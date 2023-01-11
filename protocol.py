import socket
import zlib
from random import choices
from typing import Tuple
import tkinter as tk


def include_flag(flag: str, flags: str) -> str:
    res = list(flags)
    if flag == "ACK":
        res[7] = "1"
    elif flag == "PSH":
        res[6] = "1"
    elif flag == "SYN":
        res[5] = "1"
    elif flag == "FIN":
        res[4] = "1"
    elif flag == "RST":
        res[3] = "1"
    elif flag == "KA":
        res[2] = "1"
    elif flag == "ERR":
        res[1] = "1"
    elif flag == "REQ":
        res[0] = "1"

    return "".join(res)


# function that returns us the sector of the heading with flags values
def set_flags(flags: list[str]) -> bytes:
    res = "00000000"  # starter of our flag sector which takes precisely 8 bits

    for f in flags:
        res = include_flag(f, res)  # including every flag to our 8-bit array of values

    res = int(res, 2)
    return res.to_bytes(1, "big")


# function to calculate sum of two binary strings
def add_binary_nums(x, y):
    max_len = max(len(x), len(y))

    x = x.zfill(max_len)
    y = y.zfill(max_len)

    # initialize the result
    result = ''

    # initialize the carry
    carry = 0

    # Traverse the string
    for i in range(max_len - 1, -1, -1):
        r = carry
        r += 1 if x[i] == '1' else 0
        r += 1 if y[i] == '1' else 0
        result = ('1' if r % 2 == 1 else '0') + result
        carry = 0 if r < 2 else 1  # Compute the carry.

    if carry != 0:
        result = '1' + result

    return result


# function that finds one's complement of the binary string
def get_ones_complement(starter: str) -> str:
    res = list(starter)

    for s in range(len(res)):
        if res[s] == "1":
            res[s] = "0"
        elif res[s] == "0":
            res[s] = "1"

    return "".join(res)


def get_binary(starter: str) -> str:
    res = ""
    for i in starter:
        t = str(i)
        res += str(bin(ord(t)))[2:]

    # print(f"Fragment binary form: {res[2:]}")
    return res


# function that calculates checksum of the payload
def calculate_checksum(payload) -> bytes:
    fragments = []
    cnt = 4

    # dividing our payload into 32-bit/4-byte fragments:
    while cnt < len(payload):
        fragments.append(payload[cnt-4:cnt])
        cnt += 4
    fragments.append(payload[cnt-4:])

    # summing all the fragments
    res = get_binary(str(fragments[0]))
    for i in range(1, len(fragments)):
        res = add_binary_nums(res, get_binary(fragments[i]))

    # if result is bigger than 32 bits then we take bits from start and add it to the result
    while True:
        if len(res) > 32:
            main_p = str(res[len(res)-33:len(res)])
            to_add = str(res[0:len(res)-33])
            res = add_binary_nums(main_p, to_add)
        else:
            break

    # now we only need to find the one's complement from our result and return checksum
    res = get_ones_complement(res)

    # print(res)
    res = int(res, 2)

    return res.to_bytes(4, "big")


# function that writes binary representation of length of the payload
def get_length(payload: int) -> bytes:
    return payload.to_bytes(2, "big")


# function that adds to the beginning of the payload heading of the protocol
def apply_protocol(payload, flags: list[str], message_type: str, damage: bool) -> bytes:

    res: bytes = b""
    # first thing in our protocol is flags
    res += set_flags(flags)

    # then we write down the checksum

    # checksum function for text messages
    if message_type == "T":
        res += calculate_checksum(payload)
    # Using crc32 checksum for Files
    elif message_type == "F":
        res += zlib.crc32(payload).to_bytes(4, "big")

    res += message_type.encode('utf-8')

    # and writing down the payload
    if message_type == "T":
        payload = payload.encode("utf-8")

    if damage is True:
        if len(payload) != 1:
            damaged = payload[len(payload) // 2:] + payload[:len(payload) // 2]
            res += damaged
        else:
            damaged = b';'
            res += damaged
    else:
        res += payload

    return res


def establish_con(server_addr: Tuple[str, int], sock: socket) -> bool:
    # padding string filled with zeros
    pad = "".join(choices("0", k=15))
    while True:
        print("Sending SYN signal to the server")
        sock.sendto(apply_protocol(pad, ["SYN"], 'T', False), server_addr)
        try:
            reply, addr = sock.recvfrom(1500)
            # if int.from_bytes(list(reply[0])[0], "big") == 5:
            if reply[0] == 5:
                print("SYN, ACK signal has been received\nSending ACK signal")
                sock.sendto(apply_protocol(pad, ["ACK"], 'T', False), server_addr)
                print("Connection established")
                return True
        except socket.timeout:
            print("Didn't receive SYN, ACK from server")
            continue


def finish_con(participant_addr: Tuple[str, int], sock: socket) -> bool:
    # closing connection with the wish of client

    # padding string filled with zeros
    pad = "".join(choices("0", k=15))
    print("Sending FIN signal")
    sock.sendto(apply_protocol(pad, ["FIN"], 'T', False), participant_addr)
    while True:
        try:
            reply, addr = sock.recvfrom(1500)
            # if we receive reply with FIN and ACK flags then we send ACK and connection is closed
            # if int.from_bytes(list(reply[0])[0], "big") == 9:
            if reply[0] == 9:
                print("FIN, ACK signal has been received, replying with ACK")
                sock.sendto(apply_protocol(pad, ["ACK"], 'T', False), participant_addr)
                return True
            elif reply[0] == 16:
                print("RST signal has been received, interrupting connection")
                return False
            elif reply[0] == 32:
                print("KA has been received, resending FIN signal")
                sock.sendto(apply_protocol(pad, ["FIN"], 'T', False), participant_addr)
                continue
            else:
                print(f"Other signal has been received: {reply[0]}")
                continue
        except socket.timeout:
            print("Didn't receive any signal from participant\n Sending RST signal")
            sock.sendto(apply_protocol(pad, ["RST"], 'T', False), participant_addr)
            return False


def handle_fin(participant_addr: Tuple[str, int], sock: socket) -> bool:
    # handling FIN signal from the server

    pad = "".join(choices("0", k=15))
    print("\nReceived FIN signal, \nSending FIN, ACK signal")
    sock.sendto(apply_protocol(pad, ["FIN", "ACK"], 'T', False), participant_addr)
    while True:
        try:
            reply, addr = sock.recvfrom(1500)
            # if int.from_bytes(list(reply[0])[0], "big") == 1:
            if reply[0] == 1:
                # we received ACK - connection is closed
                print("ACK signal has been received, connection is closed")
                return True
            elif reply[0] == 64:
                # we received ERR signal, resending FIN, ACK signal
                sock.sendto(apply_protocol(pad, ["FIN", "ACK"], 'T', False), participant_addr)
                print("ERR signal has been received\nSending FIN, ACK signal")
                continue
            else:
                # else we send RST signal and closing socket
                print("Received not ACK, interrupting connection")
                sock.sendto(apply_protocol(pad, ["RST"], 'T', False), participant_addr)
                return False
        except socket.timeout:
            print("Timed out, interrupting connection")
            sock.sendto(apply_protocol(pad, ["RST"], 'T', False), participant_addr)
            return False


def req_switch(participant_addr, s: socket) -> bool:
    pad = "".join(choices("0", k=15))
    s.sendto(apply_protocol(pad, ["REQ"], 'T', False), participant_addr)
    print("REQ signal has been sent")

    while True:

        try:
            reply, addr = s.recvfrom(1500)

            if reply[0] == 129:
                print("REQ, ACK signal has been received, sending ACK signal and switching role")
                s.sendto(apply_protocol(pad, ["ACK"], 'T', False), participant_addr)
                return True
            elif reply[0] == 64:
                print("Participant refused to switch")
                return False
            elif reply[0] == 32:
                print("KA has been received, resending REQ signal")
                s.sendto(apply_protocol(pad, ["REQ"], 'T', False), participant_addr)
                continue
            else:
                print(f"Received other signal: {reply[0]}")
                continue
        except socket.timeout:
            print("Didn't receive any response")
            s.sendto(apply_protocol(pad, ["REQ"], 'T', False), participant_addr)
            print("REQ signal has been sent")
            continue


cho = False


def yes(root):
    global cho

    cho = True
    root.destroy()
    return


def get_choice() -> bool:
    global cho
    cho = False
    root = tk.Tk()

    # get the screen dimension
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # find the center point
    center_x = int(screen_width / 2 - 515 / 2)
    center_y = int(screen_height / 2 - 200 / 2)

    root.geometry(f'515x200+{center_x}+{center_y}')

    question = tk.Label(root, text="Do you agree to switch roles?", font=('Times', 24))
    question.grid(row=1, column=2)

    y = tk.Button(root, text="Yes", font=('Times', 24), command=lambda: yes(root))
    y.grid(row=5, column=1)

    n = tk.Button(root, text="No", font=('Times', 24), command=lambda: root.destroy())
    n.grid(row=5, column=3)
    root.attributes("-topmost", True)
    root.mainloop()

    return cho


def handle_switch(participant_addr, s: socket) -> bool:
    pad = "".join(choices("0", k=15))

    # choice = input("Do you agree to switch role? (y/n): ")
    # ================================================================================================================
    choice = get_choice()
    # ================================================================================================================
    if choice is True:
        s.sendto(apply_protocol(pad, ["REQ", "ACK"], 'T', False), participant_addr)
        print("REQ, ACK signal has been sent")
        while True:
            try:
                reply, addr = s.recvfrom(1500)

                if reply[0] == 1:
                    print("ACK signal has been received, switching role")
                    return True
            except socket.timeout:
                print("Didn't receive any response")
                s.sendto(apply_protocol(pad, ["REQ", "ACK"], 'T', False), participant_addr)
                print("REQ, ACK signal has been sent")
                continue
    else:
        s.sendto(apply_protocol(pad, ["ERR"], 'T', False), participant_addr)
        print("You have chosen to refuse to switch")
        return False
