#!/usr/bin/env python3
# src/app/network/tools.py

import shutil
import socket
import re
from typing import Optional
from PyQt5.QtWidgets import QApplication

try:
    from app.helper import Helper
except ImportError:
    from helper import Helper

class Tools:

    def __init__(
        self,
        helper: Optional[Helper] = None
    ):

        # Initialize QObject
        super().__init__()

        # --- auto-wire from QApplication if not provided ---
        if helper is None:
            app = QApplication.instance()
            if app is None:
                raise RuntimeError("Client must be created after QApplication/Application.")
            # narrow the type for linters / IDEs
            # no runtime import to avoid circular imports
            helper = helper or app.helper          # type: ignore[attr-defined]

        # Helper
        self._helper: Helper = helper

        # OS type
        self._os: str = self._helper.get_os()

    def ping(self, host):
        args = []
        if self._os == "windows":
            args = ["ping", "-n", "1", "-w", "1000"]
        elif self._os == "linux":
            args = [shutil.which("ping") or "ping", "-c", "1", "-W", "1"]
        else:  # macOS
            args = ["/sbin/ping", "-c", "1", "-t", "1"]
        return self._helper.run(args + [host])[0] == 0

    def traceroute(self,host):
        args = []
        if self._os == "windows":
            args = ["tracert", "-d", "-h", "30", "-w", "1000", host]
        elif self._os == "macos":
            args = ["/usr/sbin/traceroute", "-n", "-m", "30", "-w", "1", host]
        else:  # linux
            args = [shutil.which("traceroute") or "traceroute", "-n", "-m", "30", "-w", "1", host]
        rc, out = self._helper.run(args)
        if rc != 0:
            return None
        hops = []
        for line in out.splitlines():
            line = line.strip()
            if re.match(r"^\d+\s+", line):
                parts = line.split()
                if len(parts) >= 2:
                    hop_ip = parts[1]
                    hops.append(hop_ip)
        return hops

    def nslookup(self, host):
        args = []
        if self._os == "windows":
            args = ["nslookup", host]
        else:
            args = [shutil.which("nslookup") or "nslookup", host]
        rc, out = self._helper.run(args)
        if rc != 0:
            return False, ""
        m = re.search(r"Address:\s+([0-9.]+)", out)
        if m:
            return True, m.group(1)
        return False, ""

    def gateway(self):
        # Windows: parse ipconfig output
        if self._os == "windows":
            rc, out = self._helper.run(["ipconfig"])
            if rc != 0:
                return None

            # Typical line: "Default Gateway . . . . . . . . . : 192.168.1.1"
            m = re.search(r"Default Gateway[ .:]*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", out)
            if m:
                return m.group(1)
            return None

        # Linux: use "ip route"
        if self._os == "linux":
            rc, out = self._helper.run(["ip", "route"])
            if rc != 0:
                return None

            for line in out.splitlines():
                line = line.strip()
                # e.g. "default via 192.168.1.1 dev eth0 ..."
                if line.startswith("default "):
                    m = re.search(r"default\s+via\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", line)
                    if m:
                        return m.group(1)
            return None

        # macOS: use "route -n get default"
        # self._os assumed "macos" for your helper
        rc, out = self._helper.run(["route", "-n", "get", "default"])
        if rc != 0:
            return None

        # Typical line: "gateway: 192.168.1.1"
        m = re.search(r"gateway:\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", out)
        if m:
            return m.group(1)
        return None

    def host(self):
        try:
            return socket.gethostname()
        except Exception:
            return None

    def ip(self):
        ips = []

        # ---------------------------
        # Windows
        # ---------------------------
        if self._os == "windows":
            rc, out = self._helper.run(["ipconfig"])
            if rc == 0:
                # "IPv4 Address. . . . . . . . . . . : 192.168.1.24"
                for line in out.splitlines():
                    m = re.search(r"IPv4 Address[.\s:]*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", line)
                    if m:
                        ip = m.group(1)
                        if not ip.startswith("127.") and not self.apipa(ip):
                            ips.append(ip)
            return ips

        # ---------------------------
        # Linux
        # ---------------------------
        if self._os == "linux":
            rc, out = self._helper.run([shutil.which("ip") or "ip", "addr"])
            if rc == 0:
                # Lines like: "inet 192.168.1.24/24 brd ... "
                for line in out.splitlines():
                    line = line.strip()
                    if line.startswith("inet "):
                        m = re.search(r"inet\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", line)
                        if m:
                            ip = m.group(1)
                            if not ip.startswith("127.") and not self.apipa(ip):
                                ips.append(ip)
                return ips

            # Fallback to ifconfig if ip fails
            rc, out = self._helper.run([shutil.which("ifconfig") or "ifconfig", "-a"])
            if rc == 0:
                for line in out.splitlines():
                    line = line.strip()
                    # "inet 192.168.1.24 netmask 0xffffff00 ..."
                    if line.startswith("inet "):
                        m = re.search(r"inet\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", line)
                        if m:
                            ip = m.group(1)
                            if not ip.startswith("127.") and not self.apipa(ip):
                                ips.append(ip)
                return ips

        # ---------------------------
        # macOS
        # ---------------------------
        if self._os == "macos":
            # macOS standard is ifconfig; there is usually no ip(8)
            rc, out = self._helper.run([shutil.which("ifconfig") or "ifconfig"])
            if rc == 0:
                for line in out.splitlines():
                    line = line.strip()
                    # Lines with IPv4 usually look like:
                    # "inet 192.168.1.24 netmask 0xffffff00 broadcast 192.168.1.255"
                    if line.startswith("inet "):
                        m = re.search(r"inet\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", line)
                        if m:
                            ip = m.group(1)
                            if not ip.startswith("127.") and not self.apipa(ip):
                                ips.append(ip)
                return ips

        # ---------------------------
        # Fallback: use gethostbyname_ex
        # ---------------------------
        try:
            hostname = socket.gethostname()
            host_info = socket.gethostbyname_ex(hostname)
            for ip in host_info[2]:
                if not ip.startswith("127.") and not self.apipa(ip):
                    ips.append(ip)
        except Exception:
            pass

        return ips

    def mac(self):
        macs = set()

        def _norm(m: str) -> str:
            # Normalize to aa:bb:cc:dd:ee:ff
            m = m.strip().lower().replace('-', ':')
            parts = m.split(':')
            if len(parts) != 6:
                return m
            return ':'.join(p.zfill(2) for p in parts)

        # ---------------------------
        # Windows: use getmac
        # ---------------------------
        if self._os == "windows":
            rc, out = self._helper.run(["getmac", "/v", "/fo", "csv"])
            if rc == 0:
                # Lines contain something like:
                # "Connection Name","Network Adapter","Physical Address","Transport Name"
                for line in out.splitlines():
                    # Look for MAC patterns
                    for m in re.findall(r'([0-9A-Fa-f]{2}([-:])[0-9A-Fa-f]{2}(?:\2[0-9A-Fa-f]{2}){4})', line):
                        macs.add(_norm(m[0]))
                return sorted(macs)

            # Fallback: ipconfig /all
            rc, out = self._helper.run(["ipconfig", "/all"])
            if rc == 0:
                for line in out.splitlines():
                    # "Physical Address. . . . . . . . . : 00-11-22-33-44-55"
                    mm = re.search(r'Physical Address[.\s:]*([0-9A-Fa-f\-:]{17})', line)
                    if mm:
                        macs.add(_norm(mm.group(1)))
                return sorted(macs)

            return []

        # ---------------------------
        # Linux / macOS: ip link
        # ---------------------------
        rc, out = self._helper.run([shutil.which("ip") or "ip", "link"])
        if rc == 0:
            # Lines with "link/ether 00:11:22:33:44:55"
            for line in out.splitlines():
                mm = re.search(r'link/ether\s+([0-9A-Fa-f:]{17})', line)
                if mm:
                    macs.add(_norm(mm.group(1)))
            if macs:
                return sorted(macs)

        # Fallback: ifconfig
        rc, out = self._helper.run([shutil.which("ifconfig") or "ifconfig", "-a"])
        if rc == 0:
            for line in out.splitlines():
                # Look for MAC in common formats
                for m in re.findall(r'([0-9A-Fa-f]{2}([-:])[0-9A-Fa-f]{2}(?:\2[0-9A-Fa-f]{2}){4})', line):
                    macs.add(_norm(m[0]))

        return sorted(macs)

    def wan(self):
        # IPv4 regex
        ipv4_re = re.compile(r'\b([0-9]{1,3}(?:\.[0-9]{1,3}){3})\b')

        # ---------------------------
        # Non-Windows: use dig
        # ---------------------------
        if self._os in ("linux", "macos"):
            dig_path = shutil.which("dig") or "dig"
            rc, out = self._helper.run(
                [dig_path, "+short", "myip.opendns.com", "@resolver1.opendns.com"]
            )
            if rc == 0:
                for line in out.splitlines():
                    m = ipv4_re.search(line)
                    if m:
                        return m.group(1)
            # If dig is missing or fails, fall through to nslookup below.

        # ---------------------------
        # Windows or fallback: nslookup
        # ---------------------------
        rc, out = self._helper.run([
            shutil.which("nslookup") or "nslookup",
            "myip.opendns.com",
            "resolver1.opendns.com",
        ])
        if rc == 0:
            # Typical output has several "Address:" lines; the last IPv4 is usually the WAN IP.
            candidates = []
            for line in out.splitlines():
                m = ipv4_re.search(line)
                if m:
                    ip = m.group(1)
                    # Skip the resolver's own IP (208.67.x.x) if you want only your WAN IP
                    if not ip.startswith("208.67."):
                        candidates.append(ip)
            if candidates:
                return candidates[-1]

        return None

    def apipa(self, ip):
        if not isinstance(ip, str):
            return False

        parts = ip.split(".")
        if len(parts) != 4:
            return False

        try:
            octets = [int(p) for p in parts]
        except ValueError:
            return False

        # 169.254.x.x
        return (octets[0] == 169 and octets[1] == 254)

    def nmap(self, host, ports):
        # Normalize `ports` into a list of ints
        port_list = []

        if isinstance(ports, int):
            port_list = [ports]

        elif isinstance(ports, (list, tuple)):
            for p in ports:
                try:
                    port_list.append(int(p))
                except Exception:
                    pass

        elif isinstance(ports, str) and "-" in ports:
            # range like "20-30"
            try:
                start, end = ports.split("-", 1)
                start = int(start)
                end = int(end)
                port_list = list(range(start, end + 1))
            except Exception:
                return {}

        else:
            # last fallback
            try:
                port_list = [int(ports)]
            except Exception:
                return {}

        # No valid ports
        if not port_list:
            return {}

        results = {}

        # -------------------------------------------------------
        # Try using nmap (fast, reliable, bulk scan)
        # -------------------------------------------------------
        nmap_bin = shutil.which("nmap")
        if nmap_bin:
            # Build port string: "22,80,443"
            port_str = ",".join(str(p) for p in port_list)

            args = [
                nmap_bin,
                "-p", port_str,
                "-T4",
                "-Pn",
                host
            ]

            rc, out = self._helper.run(args)
            if rc == 0:
                # Parse output for each port
                for port in port_list:
                    pattern = rf"^{port}/\w+\s+open\b"
                    is_open = False
                    for line in out.splitlines():
                        if re.search(pattern, line.strip(), re.IGNORECASE):
                            is_open = True
                            break
                    results[str(port)] = is_open

                return results

        # -------------------------------------------------------
        # Fallback: try TCP connect for each port
        # -------------------------------------------------------
        import socket
        for port in port_list:
            try:
                with socket.create_connection((host, port), timeout=1.0):
                    results[str(port)] = True
            except Exception:
                results[str(port)] = False

        return results
