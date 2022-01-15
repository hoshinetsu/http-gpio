import socket as sck
import lgpio as dio
import time
import math
from threading import *

# Info: the server must be ran as root.
IN = 0
OUT = 1
LO = 0
HI = 1


# CONFIG
# 	GPIO Access Control List
# 	Format: pin_id:(mode, initial_state)
gpioacl = {23: (OUT, LO), 22: (OUT, LO)}

# IP Address for the server to listen on
iface = '0.0.0.0'
port = 8080
# END of CONFIG



chip = dio.gpiochip_open(0)
for key in gpioacl:
    if gpioacl[key][0] == 1:
        dio.gpio_claim_output(chip, key, level=gpioacl[key][1])
    else:
        dio.gpio_claim_input(chip, key)

rmsg = {200: "OK", 404: "Not Found",
        400: "Bad Request", 418: "I'm a teapot uwu."}

headers = "Connection: close\r\n"
headers += "Server: RPi-GPIO ver. 1.1\r\n"
cachectl = {True: "Cache-Control: max-age=86400\r\n",
            False: "Cache-Control: no-cache\r\n"}


def load(resource, mode=""):
    with open(resource, "r" + mode) as file:
        tmp = file.read()
        print("Loaded resource:", resource)
    return tmp


print("Loading static resources..")
header = load("header.htm")
footer = load("footer.htm")
index = load("index.htm").encode()

mime = ["text/html; charset=UTF-8", "text/css", "image/png",
        "image/jpeg", "application/x-font-opentype", "image/svg+xml"]
staticResources = {"style.css": [load("style.css").encode(), 1], "": [index, 0], "bg.jpg": [
    load("bg.jpg", "b"), 3], "switch.svg": [load("switch.svg", "b"), 5], "DTM-Mono.otf": [load("DTM-Mono.otf", "b"), 4], "toggle.png": [load("toggle.png", "b"), 2]}


class Client(Thread):
    def __init__(self, cli, addr):
        Thread.__init__(self)
        self.cli = cli
        self.code = 200
        self.addr = addr
        self.response = header
        self.start()

    def res(self, txt, fin=False):
        self.response += txt
        if fin:
            self.response += footer

    def generateHeaders(self, mt, cache):
        return f"HTTP/1.1 {self.code} {rmsg[self.code]}\r\nContent-Type: {mime[mt]}\r\n{headers}{cachectl[cache]}\r\n"

    def transmit(self, cli, data, mt=0, cache=True):
        cli.send(self.generateHeaders(mt, cache).encode())
        cli.send(data)
        cli.close()

    def respond(self, cli, cach=True):
        self.transmit(cli, self.response.encode(), cache=cach)

    def run(self):
        stime = time.time()
        cli = self.cli
        print("Client", addr)

        req = cli.recv(1024).decode()

        if not "GET /" in req:
            self.code = 400
            self.res("Bad request - accept GET", True)
            self.respond(cli, False)
            return

        get = req.find("GET /") + 5
        req = req[get:req.find(" ", get)]
        if not req.startswith("ctl"):
            if req in staticResources:
                self.code = 200
                self.transmit(
                    cli, staticResources[req][0], staticResources[req][1])
                return

            self.code = 404
            self.res(
                f"<li class='error'><p>Resource \"{req}\" not found\r\n</p></li>", True)
            self.respond(cli, False)
            return
        try:
            par = req[req.find("?")+1:]
            spl = par.split("&")

            params = ""
            split = []

            for param in spl:
                if not param.startswith("gpio"):
                    self.res(
                        f"<li class='error'><p>Invalid param \"{param}\" - skip</p></li>")
                    continue
                if "=" in param:
                    a, b = param.split("=", 1)
                    try:
                        a = int(a[4:])
                        if not a in gpioacl:
                            self.res(
                                f"<li class='error'><p>Forbidden GPIO {a} - skip</p></li>")
                            continue
                        b = int(b)
                    except Exception as e:
                        self.res(
                            f"<li class='error'><p>Number format error: \"{e}\" - skip</p></li>")
                else:
                    a = param
                    try:
                        a = int(a[4:])
                        if not a in gpioacl:
                            self.res(
                                f"<li class='error'><p>Forbidden GPIO {a} - skip</p></li>")
                            continue
                        b = dio.gpio_read(chip, a)
                        param = f"{param}={b}"
                    except Exception as e:
                        self.res(
                            f"<li class='error'><p>Error while figuring out param: \"{e}\" - skip</p></li>")
                        continue
                split.append(param)
                params += param + "&"
            params = params[:-1]
            for param in split:
                a, b = param.split("=", 1)
                a = int(a[4:])
                b = int(b)
                if gpioacl[a][0] == OUT:
                    if b <= 0:
                        dio.gpio_write(chip, a, LO)
                        self.res(
                            f'<li><a href="?{params.replace(param, params[:-1] + "1")}"><div class="control-on">GPIO {a}: <span class="green">ON</span></div></a></li>')
                    else:
                        dio.gpio_write(chip, a, HI)
                        self.res(
                            f'<li><a href="?{params.replace(param, params[:-1] + "0")}"><div class="control-off">GPIO {a}: <span class="red">OFF</span></div></a></li>')
                    continue
                self.res(
                    f"<li class='error'><p>Bad GPIO mode for {a} - skip</p></li>")
            self.res(
                f"<li><p class='timing'>Site generated in {str(time.time() - stime)[0:8]}s</p></li>", True)
        except Exception as e:
            self.res(
                f"<li class='error'><p>Error while processing request: {e}</p></li>")
        finally:
            self.respond(cli, False)


srv = sck.socket(sck.AF_INET, sck.SOCK_STREAM)
srv.setsockopt(sck.SOL_SOCKET, sck.SO_REUSEADDR, 1)
srv.bind((iface, port))
srv.listen()
print(f"Started listening on /{iface}:{port}")

while True:
    try:
        cli, addr = srv.accept()
        Client(cli, addr)
    except Exception as e:
        print(e)
