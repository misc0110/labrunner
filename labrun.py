#!/usr/bin/python3
import paramiko
import yaml
import sys
import time
import socket
from select import select
import click
import logging
from colorlog import ColoredFormatter
import os
from multiprocessing import Pool, TimeoutError


logger = None

def setup_logger():
    formatter = ColoredFormatter(
        "%(log_color)s%(levelname)-8s%(reset)s %(white)s%(message)s",
        datefmt=None,
        reset=True,
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red',
        }
    )

    logger = logging.getLogger('log')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    return logger


class ParaProcess():
    def __init__(self):
        self.returncode = 0


class ParaProxy(paramiko.proxy.ProxyCommand):
    def __init__(self, stdin, stdout, stderr):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.timeout = None
        self.channel = stdin.channel
        self.process = ParaProcess()

    def send(self, content):
        try:
            self.stdin.write(content)
        except IOError as exc:
            raise socket.error("Error: {}".format(exc))
        return len(content)

    def recv(self, size):
        try:
            buffer = b''
            start = time.time()

            while len(buffer) < size:
                select_timeout = self._calculate_remaining_time(start)
                ready, _, _ = select([self.stdout.channel], [], [],
                                     select_timeout)
                if ready and self.stdout.channel is ready[0]:
                      buffer += self.stdout.read(size - len(buffer))

        except socket.timeout:
            if not buffer:
                raise

        except IOError as e:
            return ""

        return buffer

    def _calculate_remaining_time(self, start):
        if self.timeout is not None:
            elapsed = time.time() - start
            if elapsed >= self.timeout:
                raise socket.timeout()
            return self.timeout - elapsed
        return None

    def close(self):
        self.stdin.close()
        self.stdout.close()
        self.stderr.close()
        self.channel.close()


class RemoteJob():
    def __init__(self, machine, copy, run, get, delete, save_output, quiet, simulate, verbose):
        self.machine = machine
        self.copy = copy
        self.run = run
        self.get = get
        self.delete = delete
        self.save_output = save_output
        self.quiet = quiet
        self.simulate = simulate
        self.verbose = verbose

    def start(self):
        logger.info("Running job on %s @ %s" % (self.machine["name"], self.machine["server"]))

        auth = self.machine["auth"]

        server = self.machine.get("server", "")

        proxy = auth.get("proxy", None)
        transport = None
        try:
            if proxy:
                proxy_con = paramiko.SSHClient()
                proxy_con.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                if not self.simulate:
                    proxy_con.connect(hostname=proxy["server"], username=proxy.get("username", ""), password=proxy.get("password", None), pkey=proxy.get("key", None), key_filename=proxy.get("keyfile", None), timeout=int(proxy.get("timeout", 5)),allow_agent=False,look_for_keys=False)
                    logger.debug("Proxy command 'nc %s %d'" % (server, int(self.machine.get("port", 22))))
                    nc_con = proxy_con.exec_command("nc %s %d" % (server, int(self.machine.get("port", 22))))
                    transport = ParaProxy(*nc_con)
                logger.debug("Connected %s to proxy %s" % (proxy["username"], proxy["server"]))

            username = auth.get("username", "")
            password = auth.get("password", None)
            key = auth.get("key", None)
            keyfile = auth.get("keyfile", None)
            passphrase = auth.get("passphrase", None)

            logger.debug("Connect %s to %s (proxy: %s)" % (username, server, "Yes" if proxy else "No"))

            if not self.simulate:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(server, username=username, password=password, pkey=key, passphrase=passphrase, key_filename=keyfile, sock=transport, timeout=int(self.machine.get("timeout", 5)),allow_agent=False,look_for_keys=False)

            if len(self.copy):
                if not self.simulate:
                    ftp_client = ssh.open_sftp()
                for c in self.copy:
                    logger.info("Copying '%s' to machine" % c)
                    if not self.simulate:
                        ftp_client.put(c, c)
                        mode = os.stat(c).st_mode
                        ftp_client.chmod(c, mode)
                if not self.simulate:
                    ftp_client.close()

            if len(self.run):
                stdout_full = []
                stderr_full = []
                for r in self.run:
                    if not self.simulate:
                        _, ssh_stdout, ssh_stderr = ssh.exec_command(r)

                        stdout = []
                        for line in ssh_stdout:
                            stdout.append(line.strip())
                        stdout_full += stdout

                        stderr = []
                        for line in ssh_stderr:
                            stderr.append(line.strip())
                        stderr_full += stderr

                        if not self.quiet:
                            if len(stdout):
                                logger.info("%s stdout:" % self.machine["name"])
                                print("\n".join(stdout))
                            if len(stderr):
                                logger.warning("%s stderr:" % self.machine["name"])
                                print("\n".join(stderr))

                if not self.simulate and self.save_output:
                    with open("%s.stdout" % self.machine["name"], "w") as o:
                        o.write("\n".join(stdout_full) + "\n")
                    if len(stderr_full):
                        with open("%s.stderr" % self.machine["name"], "w") as o:
                            o.write("\n".join(stderr_full) + "\n")
                    else:
                        if os.path.exists("%s.stderr" % self.machine["name"]):
                            os.unlink("%s.stderr" % self.machine["name"])


            if len(self.get):
                if not self.simulate:
                    ftp_client = ssh.open_sftp()
                for g in self.get:
                    logger.info("Retrieving '%s'" % g)
                    if not self.simulate:
                        ftp_client.get(g, "%s_%s" % (self.machine["name"], g))
                if not self.simulate:
                    ftp_client.close()

            if len(self.copy) and self.delete:
                if not self.simulate:
                    ftp_client = ssh.open_sftp()
                for c in self.copy:
                    logger.info("Deleting '%s' from machine" % c)
                    if not self.simulate:
                        ftp_client.remove(c)
                if not self.simulate:
                    ftp_client.close()
        except Exception as e:
            logger.error("Connection to %s failed!" % self.machine["name"])
            print(e)


def job_runner(job):
    job.start()

@click.command()
@click.option('-c', '--copy', default=[], multiple=True, help='Copy file to remote machine.')
@click.option('-r', '--run', default=[], multiple=True, help='The command to run.')
@click.option('-g', '--get', default=[], multiple=True, help='Download file from remote machine.')
@click.option('-d', '--delete', is_flag=True, help='Delete copied files afterwards.')
@click.option('-S', '--save-output', 'save_output', is_flag=True, help='Save stdout as file.')
@click.option('-q', '--quiet', is_flag=True, help='Do not display stdout.')
@click.option('-G', '--group', default=[], multiple=True, help='Group of machines to run on.')
@click.option('-m', '--machine', default=[], multiple=True, help='Machine to run on.')
@click.option('-a', '--all', 'all_machines', is_flag=True, help='Run on all machines.')
@click.option('-s', '--simulate', is_flag=True, help='Simluate only, do not connect.')
@click.option('-v', '--verbose', is_flag=True, help='Show debug information.')
@click.option('-M', '--machine-list', 'machine_list', default="machines.yaml", help='YAML file containing the remote-machine configurations.')
@click.option('-A', '--auth', default="auth.yaml", help='YAML file containing the authentication details (including proxies).')
@click.option('-p', '--parallelize', is_flag=True, help='Connect to remote machines in parallel.')
def main(copy, run, get, delete, save_output, quiet, group, machine, all_machines, simulate, verbose, machine_list, auth, parallelize):
    global logger
    logger = setup_logger()
    if verbose:
        logger.setLevel(logging.DEBUG)

    if not os.path.exists(auth):
        logger.critical("No %s file found! Did you adapt auth.yaml.sample and rename it to auth.yaml?" % auth)
        sys.exit(1)
    if not os.path.exists(machine_list):
        logger.critical("No %s configuration file found" % machine_list)
        sys.exit(1)

    config = open(auth).read() + "\n" + open(machine_list).read()
    setting = yaml.load(config, Loader=yaml.FullLoader)
    #print(setting["machines"])

    jobs = []

    for mlist in setting["machines"]:
        m = mlist["machine"]
        matches = False
        if m["name"] in machine:
            matches = True
        for s in group:
            if s in m["sets"]:
                matches = True
                break
        if all_machines:
            matches = True
        if not matches:
            continue
        logger.info("Creating job for %s @ %s" % (m["name"], m["server"]))
        jobs.append(RemoteJob(m, copy, run, get, delete, save_output, quiet, simulate, verbose))

    logger.info("%d jobs created!" % len(jobs))

    if parallelize:
        pool = Pool()
        pool.map(job_runner, jobs)
    else:
        for j in jobs:
            print("")
            j.start()


if __name__ == "__main__":
    main()
