# LabRunner 

A tool for transferring files and running commands on multiple remote machines. 
This is commonly needed in testing environments (labs), where one command or tool has to be run on multiple different machines in the network. 

# Installation

LabRunner is written in Python 3 and has the following dependencies: `paramiko`, `pyyaml`, `click`, and `colorlog`. They can simply be installed by running

    pip3 install -r requirements.txt


# Usage

LabRunner takes a YAML configuration file that defines the available machines in the lab. Each machine has a name, location, authentication information, and a list of groups it belong to. 
A simple use of LabRunner to get the CPU info of all machines defined in the configuration file is

    python3 labrun.py --run "cat /proc/cpuinfo" --all

## Running Commands
Commands are specified using the `--run` (or short `-r`) option. It is possible to run multiple commands by specifying the `--run` parameter multiple times, e.g. `--run "chmod +x ./test.sh" --run "./test.sh"`. The commands are executed sequentially in the order they are defined on the command line. 

## Transferring Files
LabRunner also supports transferring files before (upload) and after (download) running commands. 
To upload a file to the remote machine, use the `--copy` (short short `-c`) option. Similar to commands, it is possible to upload multiple files by specifying the option multiple times. All files are uploaded to the default working directory of ssh, which is usually the home folder of the user. 
To download files, e.g., results, after running the command(s), use the `--get` (or short `-g`) option. Again, specifying the option multiple times allows downloading multiple files. 
If you want to delete all uploaded files when everything is finished, you can specifiy the `--delete` (or short `-d`) option. 

## Filtering Machines
LabRunner can target all machines, a single machine, or a subset of machines. 
With the `--all` (or short `-a`) option, LabRunner targets all machines defined in the configuration file. 
If you want to target only one machine, use the `--machine` (or short `-m`) option followed by the name of the machine. 
The `--machine` option can also be used multiple times to select multiple machines, e.g., `-m lab01 -m lab02`. 
Machines can also be part of groups defined in the configuration file (like tags). 
Use the `--group` (or short `-G`) to select all machines in a specific group, e.g. `-G x86`. 

## Parallelize
By default, LabRunner connects to the machines sequentially to execute the commands. 
However, LabRunner also supports a parallel mode with the `--parallelize` (or short `-p`) option. 
In parallel mode, LabRunner connects to as many machines simultaneously as there are available CPU cores. 
While this usually results in faster overall execution time if there are multiple target machines, the order of the output is not sequential anymore. 
Hence, if you use parallel mode, it is recommended to also use the `--save-output` (or short `-S`) option which saves the standard output of every remote machine in its own file `<machine name>.stdout`. 

## Options
LabRunner supports the following options

| Parameter | Description |
|--|--|
| -c FILE / --copy FILE | Copy file FILE to remote machine. |
| -r CMD / --run CMD | Runs the command CMD on the remote machine. |
| -g FILE / --get FILE | Downloads the file FILE from the remote machine. |
| -d / --delete | Deletes the files copied to the machine after running the commands and downloading files. |
| -S / --save-output | Saves the stdout as a file. |
| -q / --quiet | Do not display stdout on terminal. |
| -G GROUP / --group GROUP | The group of machines to run on. |
| -m MACHINE / --machine MACHINE | The machine to run on. |
| -a / --all | Run on all machines. |
| -s / --simulate | Simulate only, do not connect to any machine. |
| -v / --verbose | Show debug information. |
| -M FILE / --machine-list FILE | The YAML file containing the remote-machine configurations (default: machines.yaml). |
| -A FILE / --auth FILE | The YAML file containing the authentication details including proxies (default auth.yaml). |
| -p / --parallelize | Connect to remote machines in parallel instead of sequentially. |

# File formats
Both the machine configuration (machines.yaml) and authentication settings (auth.yaml) are YAML files. 
If no location for an authentication or machine configuration file is provided via the command line, the tool first looks in the current working directory. 
If no file is found there, the tool tries to use the files in "~/.config/labrunner/".

## Machines.yaml
This file contains the configuration of all remote machines. Every entry looks similar to the following.

    - machine:
        name: lab01
        auth: *labauth
        server: lab01.testing.company.com
        sets: 
            - x86
            - linux
            - experiment1
            
            
* `name` is the machine name which is used for filtering (the `-m` option) and as a prefix when download files or storing the standard output. Thus, it should only contain alphanumeric characters and no spaces. 
* `auth` is a reference to an authentication information in the authentication settings (auth.yaml)
* `server` is the domain/IP of the machine
* `sets` is an optional list of groups that this machine is part of. Groups can be seen like tags. They are only used for filtering (with the `-G` option). 
* `timeout` is an optional timeout in seconds (default: 5) after which the connection has to be established.
* `port` (optional) specifies the SSH port of the machine (default: 22)

## Auth.yaml
This file contains the authentication information for the machines. There are two different types of entries in there, `auth` and `proxy`. 

### auth
The `auth` entry contains the actual authentication information. Authentication is supported via username/password and via keys. An entry looks as follows.

    - auth: &labauth
        username: <your username>
        password: <your password>
        proxy: *proxy

The identifier in the first line (here: `&labauth`) is required, as this is used in the machine configuration (machines.yaml) to reference the authentication information. 

The following fields are supported:

* `username` (required) is the username to use for the remote connection
* `password` (optional) if login via username/password is used, specify a password
* `keyfile` (optional) if login via key, specify the path to the key file here
* `passphrase` (optional) if login via, the passphrase for the key can be specified here
* `key` (optional) if login via key, you can alternatively enter the private key here
* `proxy` (optional) if a proxy is required, i.e., whether LabRunner has to connect to a different SSH machine first

### proxy
The `proxy` entry contains an SSH machine from which the connection to the remote machines can be established (typically defined as `ProxyCommand` in the ssh config).
An entry looks as follows.

    - proxy: &proxy
        username: <your username>
        password: <your password>
        server: jump.testing.company.com
        
The identifier in the first line (here: `&proxy`) is required, as this is used in `auth` entries to reference the proxy. 

The following fields are supported:

* `server` (required) the proxy server's domain/IP
* `username` (required) is the username to use for the proxy server
* `password` (optional) if login via username/password is used, specify a password
* `keyfile` (optional) if login via key, specify the path to the key file here
* `passphrase` (optional) if login via, the passphrase for the key can be specified here
* `key` (optional) if login via key, you can alternatively enter the private key here
* `timeout` (optional) timeout in seconds (default: 5) after which the connection has to be established.
* `port` (optional) specifies the SSH port of the machine (default: 22)

