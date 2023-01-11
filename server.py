import os
import socket
import zlib

from threading import Thread, Condition
from random import choices
from typing import Tuple

from protocol import apply_protocol, handle_switch, handle_fin, finish_con, req_switch
from protocol import calculate_checksum


def handle_syn(client_addr: Tuple[str, int], sock: socket) -> bool:
    # handling Syn signal from the client

    pad = "".join(choices("0", k=15))
    sock.settimeout(10)
    print("SYN signal has been received")
    while True:
        print("Sending SYN, ACK")
        sock.sendto(apply_protocol(pad, ["SYN", "ACK"], 'T', False), client_addr)
        try:
            reply, addr = sock.recvfrom(1500)
            # if int.from_bytes(list(reply[0])[0], "big") == 1:
            if reply[0] == 1:
                # we received ACK - connection is established
                print("Connection established")

                return True
        except socket.timeout:
            # else we send SYN, ACK again
            continue


pr_wait = False
break_threads = False
is_switched = False


# ser_RP stands for server receive packets
def ser_RP(s: socket, client_addr, c: Condition, path):
    global pr_wait, break_threads, is_switched

    payload, addr = s.recvfrom(1500)

    s.settimeout(8)
    is_file = False
    filename = ""
    c.acquire()
    res = b""
    fragments_cnt = 1
    errors_cnt = 0

    if path == 'l':
        path = ""

    pad = "".join(choices("0", k=15))
    while True:
        try:
            while pr_wait is True:
                c.wait()

            if break_threads is True:
                c.release()
                # print("RP thread has been stopped, connection closing process has been started")
                return

            # if received packet with PSH flag
            if payload[0] == 2:
                if chr(payload[5]) == "F":
                    checksum = zlib.crc32(payload[6:]).to_bytes(4, "big")
                else:
                    checksum = calculate_checksum(payload[6:].decode("utf-8"))

                # print(f"calculated: {checksum}\n saved:{payload[1:5]}")

                if checksum == payload[1:5]:
                    if fragments_cnt == 1:
                        # writing down the file name
                        if chr(payload[5]) == 'F':
                            is_file = True
                            filename = payload[6:].decode('utf-8')
                        else:
                            res += payload[6:]
                    else:
                        res += payload[6:]

                    print(f"Fragment number {fragments_cnt} has been received without any errors, replying with ACK")

                    while True:
                        s.sendto(apply_protocol(pad, ["ACK"], "T", False), client_addr)

                        try:
                            reply, addr = s.recvfrom(1500)
                            payload = reply
                            fragments_cnt += 1
                            break
                        # ARQ algorithm
                        except socket.timeout:
                            if break_threads is True:
                                c.release()
                                return
                            while pr_wait is True:
                                c.wait()
                            print("Didn't receive any response, resending ACK signal")
                            continue
                    continue
                else:
                    print(f"Fragment {fragments_cnt} number is damaged, sending Error signal")
                    errors_cnt += 1
                    while True:
                        s.sendto(apply_protocol(pad, ["ERR"], 'T', False), client_addr)

                        try:
                            reply, addr = s.recvfrom(1500)
                            payload = reply
                            # calculating different check sums for files and text messages
                            if chr(payload[5]) == "F":
                                checksum = zlib.crc32(payload[6:]).to_bytes(4, "big")
                            else:
                                checksum = calculate_checksum(payload[6:].decode("utf-8"))
                            if checksum == payload[1:5]:
                                break

                        except socket.timeout:
                            if break_threads is True:
                                c.release()
                                return
                            while pr_wait is True:
                                c.wait()
                            print("Didn't receive any response, resending ERR signal")
                            continue
                    continue

            elif payload[0] == 32:
                # =========================================================================================================
                # Received KA signal but last signal received was PSH - saving message
                if fragments_cnt != 1:
                    print(f"Number of fragments received: {fragments_cnt-1}\n"
                          f"Number of damaged fragments received and resend requests sent: {errors_cnt}")

                    if is_file is True:
                        f = open(path+filename, 'wb')
                        f.write(res)
                        f.close()
                        print(f"File has been received and saved as {path+filename}\n"
                              f"Length of file in Bytes is {os.stat(path+filename).st_size}")
                        filename = ""
                        is_file = False
                    else:
                        print(f"Length of message received in Bytes is {len(res)}\n"
                              f"Next message has been received: {res.decode('utf-8')}")

                    res = b""

                # =========================================================================================================
                # KA algorithm
                else:
                    print("KA received, sending ACK")

                while True:
                    s.sendto(apply_protocol(pad, ["ACK"], 'T', False), client_addr)
                    try:
                        payload, addr = s.recvfrom(1500)
                        # print("In KA condition reply received")
                        break
                    except socket.timeout:

                        if break_threads is True:
                            c.release()
                            # print("Thread is awaken and in the next line it should finish KA func")
                            # print("RP thread has been stopped, connection closing process has been started")
                            return

                        while pr_wait is True:
                            c.wait()

                        print("Didn't receive any response, resending ACK signal")
                        continue

                fragments_cnt = 1
                continue

            # =========================================================================================================
            elif payload[0] == 128:
                if handle_switch(client_addr, s) is True:
                    print("Press enter to switch role")
                    is_switched = True
                    break_threads = True
                    c.release()
                    return
                else:
                    while True:
                        try:
                            reply, addr = s.recvfrom(1500)
                            payload = reply
                            break
                        except socket.timeout:
                            if break_threads is True:
                                c.release()
                                return
                            while pr_wait is True:
                                c.wait()
                            print("Didn't receive any response, resending ERR signal")
                            s.sendto(apply_protocol(pad, ["ERR"], 'T', False), client_addr)
                            continue
                    continue

            elif payload[0] == 129:
                print("Req, Ack received in KA")
                while pr_wait is True:
                    c.wait()

                if break_threads is True:
                    c.release()
                    print("Thread is awaken and in the next line it should finish KA func")
                    # print("RP thread has been stopped, connection closing process has been started")
                    return
                continue

            # if we receive some kind of closing connection signal
            elif payload[0] == 8:
                handle_fin(client_addr, s)
                print("Connection was correctly closed\nPress enter to finish")
                break_threads = True
                c.release()
                return

            # handling FIN, ACK response,
            # it shouldn't be received here, so we respond with ERR flag and switching
            # to the right function
            elif payload[0] == 9:
                print("Sending ERR signal")
                s.sendto(apply_protocol(pad, ["ERR"], "T", False), client_addr)
                c.release()
                return

            elif payload[0] == 16:
                print("Connection was interrupted after receiving RST signal")
                break_threads = True
                c.release()
                return
        except ConnectionResetError:
            s.settimeout(30)
            print("Client has been disconnected, waiting 30 seconds for his return")
            try:
                reply, addr = s.recvfrom(1500)
                payload = reply
                s.settimeout(8)
                print("Client has returned")
                continue
            except socket.timeout:
                print("Client never returned, closing program\n"
                      "press Enter to finish")
                break_threads = True
                c.release()
                return


# function that  is being called when user chooses to be a server
def be_server(server_addr, s: socket):
    global break_threads, pr_wait, is_switched
    is_switched = False

    # Input path where files will be saved
    while True:
        path = input("Enter path where you want to save incoming files\n"
                     "(input 'l' if you want to save to project directory): ")
        if os.path.isdir(path) is True or path == 'l':
            break
        else:
            print("Path is incorrect, try again")
            continue

    # waiting for the client to open the communication
    while True:
        data, addr = s.recvfrom(1500)

        # if int.from_bytes(list(data)[0], "big") == 4:
        if data[0] == 4:
            handle_syn(addr, s)
            break

    # writing down client's addr to the variable
    client_addr = addr
    # when communication has been opened - we receive in cycle packets

    # KA thread
    c = Condition()

    t_rp = Thread(target=ser_RP, args=(s, client_addr, c, path))
    # KA thread blocks once it received a message with PSH signal
    t_rp.start()

    while True:
        ty = input("Choose your next action:\n"
                   "\t1) Switch role to the client: type \'s\'\n"
                   "\t2) Finish communication: type \'x\'\n")
        if break_threads is True:
            # s.close()
            t_rp.join()
            break_threads = False
            # print("Thread is closed")
            return is_switched, client_addr

        if ty == 'x':
            pr_wait = True
            # print("Closing connection")
            # locking up on current thread, KA thread is asleep
            c.acquire()
            if finish_con(client_addr, s) is True:
                print("Connection was correctly closed")
                # setting up break_threads marker and in some time KA thread will terminate
                break_threads = True
            else:
                print("Connection was interrupted")
            # s.close()
            pr_wait = False
            # notifying KA thread that in some time it can continue its work
            c.notify()
            # releasing lock, making KA thread work possible
            c.release()
            # joining KA thread, that means that current function will not run further until thread is finished
            t_rp.join()
            break_threads = False
            # print("Thread is closed")
            return is_switched, client_addr
        elif ty == 's':
            pr_wait = True
            c.acquire()
            if req_switch(client_addr, s) is True:
                break_threads = True
                is_switched = True
                pr_wait = False
                c.notify()
                c.release()
                t_rp.join()
                break_threads = False
                return is_switched, client_addr
            else:
                pr_wait = False
                continue

        else:
            print("Input is incorrect")
            continue




