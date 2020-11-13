function register() {
    username = document.getElementById('username').value
    password = document.getElementById('password').value
    confirm_password = document.getElementById('confirm_password').value

    if(password != confirm_password){
        alert("Password not match" + password + confirm_password)
    }
    else{
        eel.register(username,password)(username_check)
        
    }
}

function username_check(result) {
    if(result == 1){
        window.location.assign("login.html")
    }
    else{
        alert("Username exists")
    }
}


