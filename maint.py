#!/usr/bin/env python

import argparse
import glob
import os
import shutil
import subprocess
import yaml

from distutils.version import LooseVersion
from termcolor import colored

parser=argparse.ArgumentParser(description='Perform common Gentoo maintenance tasks')
parser.add_argument("-b","--backtrack",dest="backtrack",action='store_true',help="Backtrack when upgrading")
parser.add_argument("-t","--threads",dest="threads",type=int,default=os.cpu_count(),help="Number of threads to use when compiling")
operation=parser.add_mutually_exclusive_group()
operation.add_argument("-u","--upgrade",dest="upgrade",action='store_true',help="Upgrade the system")
operation.add_argument("-s","--special",dest="special",action='store_true',help="Upgrade special case packages")
operation.add_argument("-c","--clean",dest="clean",action='store_true',help="Remove outdated packages")
operation.add_argument("-k","--kernel",dest="kernel",action='store_true',help="Bump and rebuild the kernel")
operation.add_argument("-m","--modules",dest="modules",action='store_true',help="Rebuild kernel modules")
global_arguments=parser.parse_args()

with open("/usr/local/etc/{0}.yaml".format(os.path.splitext(os.path.basename(__file__))[0]),'r') as stream:
	global_configuration=yaml.safe_load(stream)

def inform(command):
	print("{0} {1}".format(colored("Executing:","white",attrs=['bold']),command))

def to_kernel_version(package):
	segments=package.split("-")
	if len(segments) < 3:
		raise ValueError("Invalid kernel package name encountered")
	package=segments[1]
	if len(segments) > 3:
		package+="-"+segments[3]
	return package

def to_package_version(version):
	version=version.split("-")
	package="linux-{0}-gentoo".format(version[0])
	if len(version) > 1:
		package+="-"+version[1]
	return package

def available_kernels():
	return subprocess.run(["eselect","kernel","list"],stdout=subprocess.PIPE,universal_newlines=True).stdout.split("\n")

def remove_outdated_kernels():
	available=[version.split(" ")[5] for version in available_kernels() if "linux" in version]
	remaining=[path for path in glob.glob("/usr/src/linux-*-gentoo*") if os.path.basename(path) not in available]
	for kernel in remaining:
		print("{0} {1}".format(colored("Removing:","white",attrs=['bold']),os.path.basename(kernel)))
		print(kernel)
		shutil.rmtree(kernel)
		kernel=os.path.basename(kernel)
		for filetype in ["config","System.map","vmlinuz"]:
			path="{0}/{1}-{2}".format(global_configuration['boot']['path'],filetype,kernel)
			if 'kernel_suffix' in global_configuration:
				path+="-"+global_configuration['kernel_suffix']
			print(path)
			if os.path.exists(path):
				os.remove(path)
		path="/lib/modules/{0}".format(kernel)
		if 'kernel_suffix' in global_configuration:
			path+="-"+global_configuration['kernel_suffix']
		print(path)
		if os.path.exists(path):
			shutil.rmtree(path)

if global_arguments.upgrade:
	subprocess.run(["emerge","--sync"])
	environment=os.environ
	environment['MAKEOPTS']="-j{0}".format(global_arguments.threads)
	command=["emerge","-uDNa","--keep-going"]
	if global_arguments.backtrack:
		command.append("--backtrack=30")
	if 'excludes' in global_configuration:
		for exclude in global_configuration['excludes']:
			command.append("--exclude={0}".format(exclude))
	command.append("@world")
	inform("MAKEOPTS='{0}' {1}".format(environment['MAKEOPTS']," ".join(command)))
	subprocess.run(command,env=environment)
	command=["emerge","-a","--keep-going","@live-rebuild"]
	inform("MAKEOPTS='{0}' {1}".format(environment['MAKEOPTS']," ".join(command)))
	subprocess.run(command,env=environment)

if global_arguments.special:
	generic_command=["emerge","-a1","--keep-going"]
	if global_arguments.backtrack:
		generic_command.append("--backtrack=30")
	for package in global_configuration['specials']:
		environment=os.environ
		environment['USE']=" ".join(package['use'])
		environment['MAKEOPTS']="-j{0}".format(global_arguments.threads)
		specific_command=generic_command + [package['name']]
		inform("USE='{0}' MAKEOPTS='{1}' {2}".format(environment['USE'],environment['MAKEOPTS']," ".join(specific_command)))
		subprocess.run(specific_command,env=environment)

if global_arguments.clean:
	subprocess.run(["emerge","-a","--depclean"])
	remove_outdated_kernels()
	environment=os.environ
	environment['MAKEOPTS']="-j{0}".format(global_arguments.threads)
	subprocess.run(["emerge","-a","@preserved-rebuild"],env=environment)
	subprocess.run(["revdep-rebuild"],env=environment)
	subprocess.run(["etc-update"])
	if "[I]" in subprocess.run(["equery","y","ghc"],stdout=subprocess.PIPE,universal_newlines=True).stdout:
		subprocess.run(["haskell-updater","-uv"])
	subprocess.run(["eselect","news","read"])

if global_arguments.kernel:
	output=available_kernels()
	current=max([to_kernel_version(version.split(" ")[5]) for version in output if "*" in version],key=LooseVersion)
	available=[to_kernel_version(version.split(" ")[5]) for version in output if "linux" in version]
	latest=max(available,key=LooseVersion)
	if latest == current:
		print("{0} {1}".format(colored("Kernel version is already latest:","white",attrs=['bold']),latest))
		exit(0)
	command=["eselect","kernel","set",to_package_version(latest)]
	inform(command)
	subprocess.run(command)
	shutil.copyfile("/usr/src/{0}/.config".format(to_package_version(current)),"/usr/src/linux/.config")
	working_directory="/usr/src/linux"
	commands=[
		["make","olddefconfig"],
		["make","-j{0}".format(global_arguments.threads)],
		["make","install"],
		["make","modules_install"],
		["grub-mkconfig","-o","{0}/grub/grub.cfg".format(global_configuration['boot']['path'])]
	]
	for command in commands:
		inform(command)
		subprocess.run(command,cwd=working_directory)

if global_arguments.modules:
	environment=os.environ
	environment['MAKEOPTS']="-j{0}".format(global_arguments.threads)
	command=["emerge","-a","--keep-going","@module-rebuild"]
	inform("MAKEOPTS='{0}' {1}".format(environment['MAKEOPTS']," ".join(command)))
	subprocess.run(command,env=environment)
