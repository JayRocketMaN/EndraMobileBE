import socket

target = "192.168.137.136"
ports = [80, 554, 1935, 5000, 8000, 8080, 8899, 9999]

print(f"Scanning target: {target}...\n")
for port in ports:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.5)
    result = sock.connect_ex((target, port))
    if result == 0:
        print(f"[+] Port {port} is OPEN")
    else:
        print(f"[-] Port {port} is closed or filtered (Error code: {result})")
    sock.close()