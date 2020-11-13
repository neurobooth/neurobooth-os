# Based on EEL

[EEL](https://github.com/samuelhwilliams/Eels) is a little Python library for making simple Electron-like offline HTML/JS GUI apps, with full access to Python capabilities and libraries.

> **Eel hosts a local webserver, then lets you annotate functions in Python so that they can be called from Javascript, and vice versa.**


### Exposing functions

In addition to the files in the frontend folder, a Javascript library will be served at `/eel.js`. You should include this in any pages:

```html
<script type="text/javascript" src="/eel.js"></script>
```

Including this library creates an `eel` object which can be used to communicate with the Python side.

Any functions in the Python code which are decorated with `@eel.expose` like this...

```python
@eel.expose
def my_python_function(a, b):
    print(a, b, a + b)
```

...will appear as methods on the `eel` object on the Javascript side, like this...

```javascript
console.log("Calling Python...");
eel.my_python_function(1, 2); // This calls the Python function that was decorated
```

Similarly, any Javascript functions which are exposed like this...

```javascript
eel.expose(my_javascript_function);
function my_javascript_function(a, b, c, d) {
  if (a < b) {
    console.log(c * d);
  }
}
```

can be called from the Python side like this...

```python
print('Calling Javascript...')
eel.my_javascript_function(1, 2, 3, 4)  # This calls the Javascript function
```

The exposed name can also be overridden by passing in a second argument. If your app minifies JavaScript during builds, this may be necessary to ensure that functions can be resolved on the Python side:

```javascript
eel.expose(someFunction, "my_javascript_function");
```

When passing complex objects as arguments, bear in mind that internally they are converted to JSON and sent down a websocket (a process that potentially loses information).

### Eello, World!

> See full example in: [examples/01 - hello_world](https://github.com/ChrisKnott/Eel/tree/master/examples/01%20-%20hello_world)

Putting this together into a **Hello, World!** example, we have a short HTML page, `web/hello.html`:

```html
<!DOCTYPE html>
<html>
  <head>
    <title>Hello, World!</title>

    <!-- Include eel.js - note this file doesn't exist in the 'web' directory -->
    <script type="text/javascript" src="/eel.js"></script>
    <script type="text/javascript">
      eel.expose(say_hello_js); // Expose this function to Python
      function say_hello_js(x) {
        console.log("Hello from " + x);
      }

      say_hello_js("Javascript World!");
      eel.say_hello_py("Javascript World!"); // Call a Python function
    </script>
  </head>

  <body>
    Hello, World!
  </body>
</html>
```

and a short Python script `hello.py`:

```python
import eel

# Set web files folder and optionally specify which file types to check for eel.expose()
#   *Default allowed_extensions are: ['.js', '.html', '.txt', '.htm', '.xhtml']
eel.init('web', allowed_extensions=['.js', '.html'])

@eel.expose                         # Expose this function to Javascript
def say_hello_py(x):
    print('Hello from %s' % x)

say_hello_py('Python World!')
eel.say_hello_js('Python World!')   # Call a Javascript function

eel.start('hello.html')             # Start (this blocks and enters loop)
```

If we run the Python script (`python hello.py`), then a browser window will open displaying `hello.html`, and we will see...

```
Hello from Python World!
Hello from Javascript World!
```

...in the terminal, and...

```
Hello from Javascript World!
Hello from Python World!
```

...in the browser console (press F12 to open).

You will notice that in the Python code, the Javascript function is called before the browser window is even started - any early calls like this are queued up and then sent once the websocket has been established.

### Return values

While we want to think of our code as comprising a single application, the Python interpreter and the browser window run in separate processes. This can make communicating back and forth between them a bit of a mess, especially if we always had to explicitly _send_ values from one side to the other.

Eel supports two ways of retrieving _return values_ from the other side of the app, which helps keep the code concise.

To prevent hanging forever on the Python side, a timeout has been put in place for trying to retrieve values from
the JavaScript side, which defaults to 10000 milliseconds (10 seconds). This can be changed with the `_js_result_timeout` parameter to `eel.init`. There is no corresponding timeout on the JavaScript side.

#### Callbacks

When you call an exposed function, you can immediately pass a callback function afterwards. This callback will automatically be called asynchrounously with the return value when the function has finished executing on the other side.

For example, if we have the following function defined and exposed in Javascript:

```javascript
eel.expose(js_random);
function js_random() {
  return Math.random();
}
```

Then in Python we can retrieve random values from the Javascript side like so:

```python
def print_num(n):
    print('Got this from Javascript:', n)

# Call Javascript function, and pass explicit callback function
eel.js_random()(print_num)

# Do the same with an inline lambda as callback
eel.js_random()(lambda n: print('Got this from Javascript:', n))
```

(It works exactly the same the other way around).

#### Synchronous returns

In most situations, the calls to the other side are to quickly retrieve some piece of data, such as the state of a widget or contents of an input field. In these cases it is more convenient to just synchronously wait a few milliseconds then continue with your code, rather than breaking the whole thing up into callbacks.

To synchronously retrieve the return value, simply pass nothing to the second set of brackets. So in Python we would write:

```python
n = eel.js_random()()  # This immediately returns the value
print('Got this from Javascript:', n)
```

You can only perform synchronous returns after the browser window has started (after calling `eel.start()`), otherwise obviously the call with hang.

In Javascript, the language doesn't allow us to block while we wait for a callback, except by using `await` from inside an `async` function. So the equivalent code from the Javascript side would be:

```javascript
async function run() {
  // Inside a function marked 'async' we can use the 'await' keyword.

  let n = await eel.py_random()(); // Must prefix call with 'await', otherwise it's the same syntax
  console.log("Got this from Python: " + n);
}

run();
```

## Asynchronous Python

Eel is built on Bottle and Gevent, which provide an asynchronous event loop similar to Javascript. A lot of Python's standard library implicitly assumes there is a single execution thread - to deal with this, Gevent can "[monkey patch](https://en.wikipedia.org/wiki/Monkey_patch)" many of the standard modules such as `time`. ~~This monkey patching is done automatically when you call `import eel`~~. If you need monkey patching you should `import gevent.monkey` and call `gevent.monkey.patch_all()` _before_ you `import eel`. Monkey patching can interfere with things like debuggers so should be avoided unless necessary.

For most cases you should be fine by avoiding using `time.sleep()` and instead using the versions provided by `gevent`. For convenience, the two most commonly needed gevent methods, `sleep()` and `spawn()` are provided directly from Eel (to save importing `time` and/or `gevent` as well).

In this example...

```python
import eel
eel.init('web')

def my_other_thread():
    while True:
        print("I'm a thread")
        eel.sleep(1.0)                  # Use eel.sleep(), not time.sleep()

eel.spawn(my_other_thread)

eel.start('main.html', block=False)     # Don't block on this call

while True:
    print("I'm a main loop")
    eel.sleep(1.0)                      # Use eel.sleep(), not time.sleep()
```