import socket

from client import be_client
from server import be_server


def main():

    # -------------------------------------------------------------------
    role = input("Welcome to my ethernet cable communication program\n\n"
                 "Choose your role:\n"
                 "\t1) Type \'c\' to be a client;\n"
                 "\t2) Type \'s\' to be a server.\n")

    while True:
        if role == "c" or role == "s":
            break
        else:
            role = input("Input role is incorrect, try again: ")
            continue

    # -------------------------------------------------------------------
    was = ""
    switched = False
    port = ''
    while True:
        server_ip = input("Enter server IP address: ")
        if server_ip == 'l':
            server_ip = 'localhost'
            port = input("Enter port: ")
            if port.isdigit() is False:
                print("Port need to be only digits")
                continue
            break
        try:
            socket.inet_aton(server_ip)
            port = input("Enter port: ")
            if port.isdigit() is False:
                print("Port need to be only digits")
                continue
            break
        except socket.error:
            print("Input is incorrect")
            continue

    if role == "c":
        was = "c"

        # setting up a socket for working above UDP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # setting up a server address--
        server_addr = (server_ip, int(port))

        s.settimeout(10)

        switched, next_ip = be_client(server_addr, s)

    else:
        was = "s"

        # setting up a socket for working above UDP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # setting up a server address
        server_addr = (server_ip, int(port))
        # bind a server to socket
        s.bind(server_addr)

        switched, next_ip = be_server(server_addr, s)

    while True:
        if switched is False:
            break
        else:
            if was == "s":
                print("Start working as client")
                switched, next_ip = be_client(next_ip, s)

                was = "c"

            elif was == "c":
                print("Start working as server")
                s.settimeout(1800)
                switched, next_ip = be_server(next_ip, s)

                was = "s"


if __name__ == '__main__':
    main()
