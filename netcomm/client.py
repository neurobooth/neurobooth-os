# Import socket module 
import socket 
from time import time  
  

def socket_message(message, node_name, wait_data=0):
    
    if node_name == "acquisition":
        host = '192.168.1.6'  
    elif node_name == "presentation":
         host = '192.168.1.14' 
    elif node_name == "control":
         host = '192.168.1.13'          
                  
    # Define the port on which you want to connect 
    port = 12347
  
    t0 = time()
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM) 
  
    # connect to server on local computer 
    s.connect((host,port)) 
    print(f"connected {time()- t0}")
    # t0 = time()
    s.send(message.encode('ascii'))    
    print(f"sent {time()- t0}")    
    # t0 = time()
    data = None
    if wait_data:
        # messaga received from server 
        data = s.recv(1024) 
        data.decode("utf-8")
   
    s.close()
    print(f"closed {time()- t0}")   
    return data    
    


def socket_time(node_name, print_flag=1):
    
    if node_name == "acquisition":
        host = '192.168.1.6'  
    elif node_name == "presentation":
         host = '192.168.1.14'  
    elif node_name == "control":
         host = '192.168.1.13'  
              
    # Define the port on which you want to connect 
    port = 12347
    
    message = "time_test"
    
    t0 = time()
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM) 
  
    # connect to server on local computer 
    s.connect((host,port)) 
    
    s.send(message.encode('ascii'))    
    
    # messaga received from server 
    data = s.recv(1024) 
    
    s.close()
    
    t1 = time()
    time_send = float( data.decode("utf-8").split("_")[-1])
    time_1way = time_send - t0
    time_2way = t1 - t0
    
    if print_flag:
        print(f"Reurn took {time_2way}, sent {time_1way}")       
    
    return  time_2way, time_1way
    
    

def Main(): 
    # local host IP '127.0.0.1' 
    host = '192.168.1.6'
  
    # Define the port on which you want to connect 
    port = 12347
  
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM) 
  
    # connect to server on local computer 
    s.connect((host,port)) 
  
    # message you send to server 
    message = f"shaurya says geeksforgeeks_{time()}"
    while True: 
  
        # message sent to server 
        s.send(message.encode('ascii')) 
  
        # messaga received from server 
        data = s.recv(1024) 
  
        # print the received message 
        # here it would be a reverse of sent message 
        print('Received from the server :',str(data.decode('ascii'))) 
  
        # ask the client whether he wants to continue 
        ans = input('\nDo you want to continue(y/n) :') 
        if ans == 'y': 
            continue
        else: 
            break
    # close the connection 
    s.close() 
  
if __name__ == '__main__': 
    Main() 