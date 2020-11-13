function login() {
  username = document.getElementById('login-username').value
  password = document.getElementById('login-password').value

  eel.login(username,password)(login_check)

}

function username_check(result) {
  if(result == 1){
      window.location.assign("login.html")
  }
  else{
      alert("Username exists")
  }
}
function login_check(result) {
  if(result == 1){
      window.location.assign("stim.html")
  }
  else{
      alert("Username or password wrong")
  }
}

function password_visibilty() {
  var x = document.getElementById("login-password");
  if (x.type === "password") {
    x.type = "text";
  } else {
    x.type = "password";
  }
}