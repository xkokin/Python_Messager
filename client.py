import random
import socket
import time
from random import choices
from threading import Condition, Thread
from typing import Tuple

from protocol import apply_protocol, handle_switch, handle_fin, establish_con, finish_con, req_switch


def fragment_message(payload: str, fragment_size: int) -> [str]:
    # cnt = 1450 - maximum size of 1 fragment, so it doesn't fragment on Link Layer
    fragment_size = fragment_size
    cnt = fragment_size
    fragments = []
    if len(payload) > fragment_size:
        print("fragmenting message")
        while cnt < len(payload):
            fragments.append(str(payload[cnt-fragment_size:cnt]))
            cnt += fragment_size
        fragments.append(str(payload[cnt-fragment_size:]))
        return fragments
    else:
        return []


def fragment_message_f(payload: bytes, fragment_size: int) -> [bytes]:
    # cnt = 1450 - maximum size of 1 fragment, so it doesn't fragment on Link Layer
    fragment_size = fragment_size
    cnt = fragment_size
    fragments = []
    if len(payload) > fragment_size:
        # print("fragmenting message")
        while cnt < len(payload):
            fragments.append(bytes(payload[cnt-fragment_size:cnt]))
            cnt += fragment_size
        fragments.append(bytes(payload[cnt-fragment_size:]))
        return fragments
    else:
        return []


ka_wait = False
is_switched = False
break_threads = False


# function that sends Keep-Alive signals to server
def cln_KA(s: socket, server_addr, c: Condition):
    global break_threads, is_switched
    c.acquire()

    pad = "".join(choices("0", k=15))
    while True:

        while ka_wait is True:
            print("Keep-Alive thread is sleeping")
            c.wait()

        if break_threads is True:
            c.release()
            return
        # ---------------------------------
        try:
            s.sendto(apply_protocol(pad, ["KA"], 'T', False), server_addr)
            # print("Sending Keep-Alive to the server")
            try:
                reply, addr = s.recvfrom(1500)
                flag = reply[0]
                # handling ACK response
                if flag == 1:
                    # print("ACK received")
                    time.sleep(5)
                    continue

                # handling switch request
                elif flag == 128:
                    if handle_switch(server_addr, s) is True:
                        is_switched = True
                        break_threads = True
                        print("Press enter to switch role")
                        c.release()
                        return
                    else:
                        continue
                # handling FIN response
                elif flag == 8:
                    if handle_fin(server_addr, s) is True:
                        print("Connection was correctly closed\nPress enter to finish")
                    else:
                        print("Connection was interrupted\nPress enter to finish")
                    break_threads = True
                    c.release()
                    return
                elif flag == 16:
                    print("Connection was interrupted after receiving RST signal")
                    break_threads = True

                    c.release()
                    return
            # ---------------------------------
            except socket.timeout:
                if break_threads is True:
                    c.release()
                    return
                print("Didn't receive any response, interrupting")
                break_threads = True

                c.release()
                return
        except ConnectionResetError:
            print("Server has been disconnected, waiting 30 seconds for his return")
            s.settimeout(30)
            try:
                reply, addr = s.recvfrom(1500)
                s.settimeout(10)
                print("Server has returned")
                continue
            except socket.timeout:
                print("Server never returned, closing program\n"
                      "press Enter to finish")
                break_threads = True
                c.release()
                return


# function that sends packets
def cln_SP(type_mess, s: socket, server_addr, payload, fragment_size, damage: bool):
    global break_threads, is_switched

    probability = 0.4
    damaged_cnt = 0
    fragments = []

    if type_mess == 'F':
        f = open(payload, "rb")
        fragments = [payload.encode('utf-8')]
        payload = b"".join(f.readlines())
        # print(f"Payload is:\n{payload}")

    if break_threads is True:
        # c.release()
        return

    if type_mess == "T":
        fragments += fragment_message(payload, int(fragment_size))
    else:
        fragments += fragment_message_f(payload, int(fragment_size))
    fragments_num = len(fragments)

    try:
        if len(fragments) != 0:
            fragments_cnt = 1
            print("Message was fragmented")
            '''
            # ----------------------------------------------------------------------------------------------------------
            # Doimplementacia Kokin
            if type_mess == 'F':
                name = bytes(fragments[0])
                fragments.pop(0)
                fragments.reverse()
                fragments.insert(0, name)
                print("Fragments for file were reversed")
            elif type_mess == 'T':
                fragments.reverse()
                print("Fragments were reversed")
            '''
            # ----------------------------------------------------------------------------------------------------------
            for i in fragments:

                if random.random() < probability and damage is True:
                    # damaging one fragment with the probability of 40 percent
                    s.sendto(apply_protocol(i, ["PSH"], type_mess, damage), server_addr)
                    damaged_cnt += 1
                    # if number of damaged packets is 3 we stop damaging packets
                    if damaged_cnt == 3:
                        damage = False
                else:
                    s.sendto(apply_protocol(i, ["PSH"], type_mess, False), server_addr)
                print(f"Fragment {fragments_cnt}/{fragments_num} has been sent")
                fragments_cnt += 1
                # ----------------------------------------------------
                # ARQ algorithm
                while True:
                    try:
                        reply, addr = s.recvfrom(1500)
                        flag_e = reply[0]
                        # if we get ERR response we simply resend last fragment until we get ACK
                        if flag_e == 64:
                            print("ERR signal has been received, resending fragment")
                            s.sendto(apply_protocol(i, ["PSH"], type_mess, False), server_addr)
                            continue
                        # if we receive RST signal - we stop sending current message and closing socket
                        elif flag_e == 16:
                            print("RST signal has been received")
                            break_threads = True
                            # c.release()
                            return
                        elif flag_e == 128:
                            if handle_switch(server_addr, s) is True:
                                is_switched = True
                                break_threads = True
                                print("Press enter to switch role")
                                return
                            else:
                                continue
                        elif flag_e == 1:
                            print("ACK signal has been received")
                            break
                    except socket.timeout:
                        s.sendto(apply_protocol(i, ["PSH"], type_mess, False), server_addr)
                # ---------------------------------------------------
        else:
            print("Message wasn't fragmented")

            # ----------------------------------------------------
            # ARQ algorithm
            while True:
                # here we don't need probability as we have only one fragment
                if damage is True:
                    s.sendto(apply_protocol(payload, ["PSH"], type_mess, damage), server_addr)
                    damage = False
                else:
                    s.sendto(apply_protocol(payload, ["PSH"], type_mess, False), server_addr)
                print("Message has been sent to the server")
                try:
                    reply, addr = s.recvfrom(1500)
                    flag_e = reply[0]

                    # if we get ERR response we simply resend last fragment until we get ACK
                    if flag_e == 64:
                        print("Error signal received, resending packet")
                        continue
                    elif flag_e == 16:
                        print("RST signal received")
                        break_threads = True
                        # c.release()
                        return
                    elif flag_e == 1:
                        print("ACK received, message sent correctly")
                        break
                except socket.timeout:
                    print("Didn't receive ACK - sending last packet again")
                    continue
            # ----------------------------------------------------
    except ConnectionResetError:
        print("Connection to server has been lost, failed to finish sending message")
        return

    # c.notify()


# function that  is being called when user chooses to be a client
def be_client(server_addr, s: socket):
    global ka_wait, break_threads, is_switched
    is_switched = False
    # requesting server address

    """# setting up a socket for working above UDP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # setting up a server address--
    server_addr = (server_ip, 12345)
    
    s.settimeout(8)"""
    client_addr = socket.gethostname()
    # establishing connection
    while True:
        est = establish_con(server_addr, s)
        if est is False:
            time.sleep(3)
        else:
            break

    # if any message hasn't been received during 10 seconds - exception raises

    # cycle where we send messages or files to server
    # ------------------------------------
    s.settimeout(30)
    # Threading
    c = Condition()

    t_ka = Thread(target=cln_KA, args=(s, server_addr, c))
    t_ka.start()

    while True:
        ty = input("Choose your next action: \n"
                   "\t1) Send text message: type \'t\'\n"
                   "\t2) Send file: type \'f\'\n"
                   "\t3) Switch role to the server: type \'s\'\n"
                   "\t4) Finish communication: type \'x\'\n")
        if break_threads is True:
            # s.close()
            t_ka.join()
            break_threads = False
            ka_wait = False
            # print("Thread is closed")
            # print("Closing client func")
            return is_switched, client_addr
        if ty == 'f':
            name = input("Enter name of your file (file need to be in the directory of project): ")

            fragment, damage = get_input()

            if break_threads is True:
                # s.close()
                t_ka.join()
                ka_wait = False
                break_threads = False
                # print("Thread is closed")
                return is_switched, client_addr
            ka_wait = True
            c.acquire()
            cln_SP('F', s, server_addr, name, fragment, damage)
            c.notify()
            c.release()
            ka_wait = False

        elif ty == 't':
            payload = input("Enter a message you want to send to the server: ")

            fragment, damage = get_input()

            if break_threads is True:
                # s.close()
                t_ka.join()
                ka_wait = False
                break_threads = False
                # print("Thread is closed")
                return is_switched, client_addr
            ka_wait = True
            c.acquire()
            cln_SP('T', s, server_addr, payload, fragment, damage)
            c.notify()
            c.release()
            ka_wait = False

        elif ty == 'x':
            ka_wait = True
            # print("Closing connection")
            c.acquire()
            if finish_con(server_addr, s) is True:
                break_threads = True
                print("Connection was correctly closed")
            else:
                print("Connection was interrupted")
            # s.close()
            ka_wait = False
            c.notify()
            c.release()
            t_ka.join()
            break_threads = False
            return is_switched, client_addr
        elif ty == 's':
            ka_wait = True
            c.acquire()
            if req_switch(server_addr, s) is True:
                # print("Trying to kill thread")
                break_threads = True
                is_switched = True
                ka_wait = False
                c.notify()
                c.release()
                t_ka.join()
                break_threads = False
                # print("Closing client func")
                return is_switched, client_addr
            else:
                ka_wait = False
                c.notify()
                c.release()
                continue

        else:
            print("Input is incorrect")
            continue


def get_input() -> Tuple[str, bool]:
    while True:
        fragment = input("Enter fragment size: ")

        if int(fragment) + 48 >= 1500 or fragment.isdigit() is False:
            print("Fragment will be fragmented on the Link Layer")
            continue
        elif fragment.isdigit() is False:
            print("Input only numbers")
            continue
        else:
            while True:
                choice = input("Do you want to send damaged fragment?(y/n): ")

                if choice == "y":
                    return fragment, True
                elif choice == "n":
                    return fragment, False
                else:
                    print("Input is incorrect")
                    continue

