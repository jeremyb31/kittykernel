#!/usr/bin/python3

#  kittykernel
#  
#  Copyright (C) 2017 by Sven Kochmann, available at Github:
#  <https://www.github.com/Schallaven/kittykernel/>
#  
#  This program is free software;  you can redistribute it and/or modify
#  it under the terms of the  GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or (at
#  your option) any later version.
#  
#  This program is  distributed in the hope that it  will be useful, but
#  WITHOUT  ANY   WARRANTY;  without   even  the  implied   warranty  of
#  MERCHANTABILITY  or FITNESS FOR  A PARTICULAR  PURPOSE.  See  the GNU
#  General Public License for more details.
#  
#  You should  have received  a copy of  the GNU General  Public License
#  along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#
#  Core routines for kittykernel, e.g. downloading a list of kernels
#
# 
#  Warning: Don't read this  source file if  you are annoyed by too many
#           comments. Read source code  of other FOSS projects  instead.
#

import os
import subprocess
import apt
import sys
import platform
import tempfile
import gettext
import re
import datetime
import configparser
_ = gettext.gettext


# Debug mode; show exception data when set to True
debugmode = False

# APT Cache object
cache = apt.Cache()

# Architecture of platform; 64bit?
platformis64bit = (platform.architecture()[0] == "64bit")

# Default config
config_default = {
    'Colors': 
        {'active': '#600000',
         'installed': '#006000',
         'downloaded': '#000060',
         'supported': '#006000',
         'expired': '#600000',
         'toexpire': '#606000'},
    'Checks':
        {'kittywarning': ''}
    }


# Convert a number of bytes to a string with respective quantities. This
# uses SI units (Ki, Mi, etc); implementation from Stackflow (Fred Cirera)
# <https://stackoverflow.com/questions/1094841/>
def sizeof_fmt(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)


# This function returns the size in bytes of the /boot directory/partition
# as tuple: (free, total); returns (0, 0) when something went wrong
def sizeof_boot():
    global debugmode
    try:
        # call df to get the size of /boot
        output_lines = subprocess.check_output("df -B 1 /boot", shell = True).decode("utf-8").strip().split('\n')

        # Should be at least two lines
        if len(output_lines) < 2:
            return (0, 0)

        # Get second line and split
        columns = list(filter(None, output_lines[1].split(' ')))

        # There should be at least 4 columns
        if len(columns) < 4:
            return (0, 0)

        # Return the 4th column (free space) and the 2nd column (total space) as integers
        return (int(columns[3]), int(columns[1]))

    # When something went really wrong...
    except Exception as e:
        if debugmode:
            print (e)
        return (0, 0)

# Opens and loads the config file from ~/.config/kittykernel/config and returns its entries as dictionaries; will return a dictionary with defaults if no file exists
def load_config():
    global debugmode

    # Config path
    config_file = os.path.expanduser("~/.config/kittykernel/config")

    # Create config object and load first the dictionary with defaults and then the config file
    config = configparser.ConfigParser()

    config.read_dict(config_default)
    config.read(config_file)

    # Create a complete dictionary of the items in config
    config_dict = {}
    for key in config:
        if key is not 'DEFAULT':
            config_dict.update({key: dict(config.items(key))})

    if debugmode:
        print(config_dict)

    return config_dict

# Saves the config file; adds the dictionary given to the default one
def save_config(options):
    # Config path
    config_file = os.path.expanduser("~/.config/kittykernel/config")

    # Create config object and load first the dictionary with defaults and then the options given as parameter
    config = configparser.ConfigParser()

    config_options = {}
    config_options.update(config_default)
    config_options.update(options)

    config.read_dict(config_options)

    with open(config_file, 'w') as configfile:
        config.write(configfile)


# Compares version numbers; adaptation of Stackflow https://stackoverflow.com/questions/1714027/version-number-comparison-in-python
def compare_versions(version1, version2):    
    def compare(a, b):
        return (a > b) - (a < b) 

    def normalize(v):
        return [int(x) for x in re.sub(r'(\.0+)*$','', v).split(".")]
        
    return compare(normalize(version1), normalize(version2))

# Updates and reopens the cache; this version uses synaptic
def refresh_cache(xwindow_id = 0):
    global cache
    # Starting synaptic with all the necessary parameters
    cmd = ["gksudo", "--", "/usr/sbin/synaptic", "--hide-main-window", "--update-at-startup", "--non-interactive", "--parent-window-id", "%d" % xwindow_id]
    comnd = subprocess.Popen(' '.join(cmd), shell=True)
    comnd.wait()

    # Reopens the list; necessary after updating
    cache.open(None)

# Just rereads the cache (reopens)
def reopen_cache():
    cache.open(None)

# Returns the current kernel as string in the format "4.10.0-28-generic"; "unknown" is returned if an exception occurred
def get_current_kernel():
    global debugmode
    try:
        # call uname to get the current kernel; truncate a little bit
        return subprocess.check_output("uname -r", shell = True).decode("utf-8").strip()
    except Exception as e:
        if debugmode:
            print (e)
        return "unknown"

# Returns the current kernel as major version in the format "4.10"; "unknown" is returned if an exception occurred
def get_current_kernel_major():
    global debugmode
    try:
        kernel_version = get_current_kernel()
        return kernel_version.split('.')[0] + "." + kernel_version.split('.')[1]
    except Exception as e:
        if debugmode:
            print (e)
        return "unknown"

# Strips the kernel version off everything except the pure numbers; allows to select maximum for subversions in resulting string;
# it removes everything after a '+' and ':' atm - probably needs better version in future
def strip_kernel_version(version, maxsubversion = 10):
    version = version.split("+", 1)[0]
    version = version.split(":", 1)[0]
    versions = version.replace("linux-image-", "").replace("-", ".").split(".")
    intversions = []

    # Test each member if it is a digit/number
    for index, ver in enumerate(versions):
        if ver.isdigit() and index < maxsubversion:
            intversions.append(ver)    

    # Return joined version as string
    return ".".join(intversions)


# Downloads and returns a list of kernels; an empty string is returned if an exception occurred
def get_kernels():
    global cache, debugmode, platformis64bit
    try:
        # First, get the current version
        current_version = get_current_kernel()        

        # DEBUG only
        if debugmode:
            print("Current architecture of system (True if 64bit): ", platform.architecture()[0], platformis64bit)

        # Create empty list to return
        kernel_list = []

        # Check the packages in the cache
        for pkg in cache:
            # Pkg is 64bit?
            pkgis64bit = (pkg.architecture() == "amd64")

            # If the package has not the right architecture... we will just go on
            if pkgis64bit != platformis64bit:
                continue

            # Create an empty dictionary object
            kernel = { 'version_major': '', 'version': '', 'package': pkg.name, 'pkg_version': '',
                       'size': 0, 'installed_size': 0, 'origins': [], 'fullname': pkg.fullname,
                       'active': False, 'installed': False, 'downloaded': False }

            # Kernel package? Check for versions 1 to 5 (the 6 is exclusive!) here
            if kernel['package'].startswith( tuple(["linux-image-"+str(x) for x in range(1,6)]) ):

                # Print name and version in debug mode
                if debugmode:
                    print(kernel['package'], strip_kernel_version(kernel['package']), pkg.architecture() )

                # Save full version and major version of package
                kernel['version'] = strip_kernel_version(kernel['package'])
                if len(kernel['version'].split('.')) > 2:
                    kernel['version_major'] = kernel['version'].split('.')[0] + "." + kernel['version'].split('.')[1]
                else:
                    # This is probably a generic image; ignore it for now
                    continue

                # Get all the flags
                kernel['active'] = (kernel['package'].replace("linux-image-", "") == current_version)
                kernel['installed'] = pkg.is_installed
                kernel['downloaded'] = pkg.has_config_files

                # Package version is either the version installed or the candidate version; no pkg_version means = not available
                if kernel['installed']:
                    kernel['pkg_version'] = pkg.installed.version                    
                elif pkg.candidate and pkg.candidate.downloadable:
                    kernel['pkg_version'] = pkg.candidate.version

                # Sizes of package
                if pkg.candidate:
                    kernel['size'] = pkg.candidate.size
                    kernel['installed_size'] = pkg.candidate.installed_size

                # Copy the origins
                for origin in pkg.candidate.origins:
                    # Ignore "now" archives
                    if origin.archive != "now":
                        kernel['origins'].append("%s (%s, %s, %s)" % (origin.label, origin.archive, origin.site, [_("trusted") if origin.trusted else _("not trusted")][0]) )

                # Join in single string
                kernel['origins'] = ", ".join(kernel['origins'])

                # Add kernel dictionary to list
                kernel_list.append(kernel)

        # Sort list by version and return it
        return sorted(kernel_list, key=lambda item: list(map(str, item['version'].split('.'))), reverse=True) 

    # If something is wrong, return an empty list
    except Exception as e:
        if debugmode:
            print (e)
            print(sys.exc_info())
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)
        return []

# Gets the kernel changelog as unicode string; string is empty, if something went wrong
def get_kernel_changelog(fullname):
    global cache
    try:
        # Is package in cache? Then, try to retrieve and return changelog
        if fullname in cache:
            return cache[fullname].get_changelog()
        else:
            return ""

    # If something is wrong, return an empty list
    except Exception as e:
        if debugmode:
            print (e)
            print(sys.exc_info())
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)
        return ""

# Reads the kernel support file provided with kittykernel to calculate the month a specific kernel is still supported
# Maybe this can be loaded from the net in future or for some distros. Ubuntu only provides a more or less convenient 
# Wiki-page (https://wiki.ubuntu.com/Kernel/Support#Ubuntu_Kernel_Support)
def get_kernel_support_times():
    # Current date as month
    now = datetime.datetime.now()
    now = now.year*12 + now.month

    # Create empty list
    supportlist = []

    # Read kernel support file (we use read.splitlines here to get rid of the "\n"; never understood why reading a text file with readlines should save the "\n"...)
    with open("/usr/lib/kittykernel/kernel_support", "r") as f:
        supportlist = f.read().splitlines()

    # Remove all empty lines from list
    supportlist = [entry for entry in supportlist if len(entry) > 0]

    # Remove all comments from list
    supportlist = [entry for entry in supportlist if not entry.startswith("#")]

    # Split lines 4 elements separated by ','; ignore all lines for which that is not possible
    supportlist = [{'origin': entry.split(',', 3)[0], 
                    'version': entry.split(',', 3)[1], 
                    'month': int(entry.split(',', 3)[2]) + int(entry.split(',', 4)[3])*12 - now} for entry in supportlist if len(entry.split(',', 3)) == 4]

    # Return list
    return supportlist


# Invokes synaptic with gksudo to do something with packages; operations is a list of tuples such as
# ('install', pkg1), ('remove', pkg2), or ('purge', pkg3); this function does not check for additional
# packages to be installed or removed (just the dependencies)
def pkg_perform_operations(operations, xwindow_id = 0):
    global debugmode

    if debugmode:
        print("pkg_perform_operations: ", operations)

    if type(operations) is not list:
        return -1

    if type(operations[0]) is not tuple:
        return -2

    try:
        # Write the list of packages in a temp file            
        f = tempfile.NamedTemporaryFile()

        # Create entry for each operation
        for op in operations:

            # Check if operation is allowed
            if op[0] not in ['install', 'remove', 'purge']:
                continue

            # Write to temp file
            f.write( ("%s\t%s\n" % (op[1], op[0])).encode("utf-8") )

            if debugmode:
                print(op)

        # Write everything to the file
        f.flush()

        # Synaptic command with gksudo
        cmd = ["gksudo", "--", "/usr/sbin/synaptic", "--hide-main-window", "--non-interactive", "--parent-window-id", "%s" % xwindow_id, "-o", "Synaptic::closeZvt=true",
                                                     "--progress-str", "\"" + _("Installing kernel packages. Please wait, this can take some time.") + "\"", 
                                                     "--finish-str", "\"" + _("The kernel was installed.") + "\"",
                                                     "--set-selections-file", f.name]

        out = subprocess.Popen(' '.join(cmd), shell=True)

        # get output
        stdout, stderr = out.communicate()

        if debugmode:
        	print(stdout.read())
        	print(stderr.read())

        return 0
        

    # If something is wrong, return error code
    except Exception as e:
        if debugmode:
            print (e)
            print(sys.exc_info())
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)
        return -3


# Installs/Removes/Purges a list of kernels with extra package (if available) and headers
def perform_kernels(fullnames, verb, xwindow_id = 0, headers = True, extras = True):
    global cache, debugmode
    try:
        if debugmode:        
            print("Perform_kernels:", fullnames, verb)

        # Our operation list
        operations = []

        # For each package name check if headers and extras are available and add to list
        for pkg in fullnames:

            # Is package in cache? Then, ask synaptic to install it
            if pkg in cache:
                # Create list of packages to install including headers, modules, extras
                pkg_list = [cache[pkg].name, cache[pkg].name.replace("-image-", "-modules-")]

                if headers:
                    pkg_list.append(cache[pkg].name.replace("-image-", "-headers-"))

                if extras:
                    pkg_list.append(cache[pkg].name.replace("-image-", "-image-extra-"))
                    pkg_list.append(cache[pkg].name.replace("-image-", "-modules-extra-"))

                # Add to operations
                for entry in pkg_list:
                    if entry in cache:
                        operations.append( (verb, entry) )

        # Perform actions
        return pkg_perform_operations(operations, xwindow_id)         

    # If something is wrong, return an empty list
    except Exception as e:
        if debugmode:
            print (e)
            print(sys.exc_info())
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)
        return -1


# Opens and loads the filter list from ~/.config/kittykernel/blacklist; will create an empty file if the file does not exist!
def load_blacklist():
    # Blacklist path
    blacklist_file = os.path.expanduser("~/.config/kittykernel/blacklist")

    # Create directory if it does not exist, yet
    os.makedirs(os.path.dirname(blacklist_file), exist_ok=True)

    # Check if user blacklist exists; if not copy from default blacklist
    if not os.path.isfile(blacklist_file):
        # Open default blacklist
        with open("/usr/lib/kittykernel/blacklist_default", "r") as f:
            default_blacklist = f.readlines()

        # Open user blacklist a write contents to it
        with open(blacklist_file, "w+") as f:
            f.writelines(default_blacklist)

    # Create empty list
    backlist = []

    # Open file; create if not exist; the seek(0) is necessary in the case that the file exists (append will move the file pointer to the end of the file!)
    # Also, we use read.splitlines here to get rid of the "\n"; never understood why reading a text file with readlines should save the "\n"...
    with open(blacklist_file, "a+") as f:
        f.seek(0)
        blacklist = f.read().splitlines()

    # Remove all empty lines from list
    blacklist = [entry for entry in blacklist if len(entry) > 0]

    # Remove all comments from list
    blacklist = [entry for entry in blacklist if not entry.startswith("#")]

    # Split lines into KEYWORD and pattern; ignore all lines for which that is not possible
    blacklist = [{'keyword': entry.split(' ', 1)[0].upper(), 'pattern': entry.split(' ', 1)[1]} for entry in blacklist if len(entry.split(' ', 1)) == 2]

    # Return cleaned list
    return blacklist

# Applies a blacklist to a kernel list
def apply_blacklist(kernels, blacklist):
    global debugmode

    # Prepare an empty list for the filtered kernels
    kernels_filtered = []

    # Each entry has to be checked
    for kernel in kernels:
        # Flag
        eliminate = False

        # Check each entry on blacklist
        for entry in blacklist:
            # Check GROUP
            if entry["keyword"] == "GROUP" and entry["pattern"] == kernel["version_major"]:
                eliminate = True
                if debugmode:
                    print("Elimnated group %s" % entry["pattern"])
                break

            # Check KERNEL
            if entry["keyword"] == "KERNEL" and re.match(entry["pattern"], kernel["package"]):
                eliminate = True
                if debugmode:
                    print("Elimnated kernel '%s' with pattern '%s'" % (kernel["package"], entry["pattern"]))
                break

        # The active kernel is _never_ filtered
        if kernel["active"]:
            eliminate = False

        # If not eliminated then add to filtered list
        if not eliminate:
            kernels_filtered.append(kernel)

    # Return filtered list
    return kernels_filtered


# Script file is run directly... then let's have some test outputs here
if __name__ == '__main__':
    print("Script was called directly. Testing...")

    # Test kernel stripping
    print("Kernel strip for 'linux-image-4.8.0-46-generic' results in: ", strip_kernel_version("linux-image-4.8.0-46-generic"))

    # Debug mode on
    debugmode = True

    # Root?
    if os.getuid() == 0:
        print("Script was called as root.")
        refresh_cache()

    print("Current kernel: ", get_current_kernel())
    print("Size of boot: ", sizeof_boot())
    kernels = get_kernels()
    print("Kernel list: ", )

    if len(kernels) > 0:
        print("Changelog of first entry %s:" % kernels[0]["fullname"], get_kernel_changelog(kernels[0]["fullname"]))

    print("Load filters: ")
    blacklist = load_blacklist()
    print(blacklist)

    print("Kernels with applied blacklist:")
    kernels = apply_blacklist(kernels, blacklist)
    for entry in kernels:
        print(entry["package"])

    print("Get support list:", get_kernel_support_times())

    print("Config parser: ")
    load_config()

