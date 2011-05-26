# ******************************************************************
# Copyright 2009-2011, Universitat Pompeu Fabra
#
# Licensed under the Non-Profit Open Software License version 3.0
# ******************************************************************

import time
from datetime import timedelta

from wok import logger
from wok.config import Config
from wok.port import PortFactory, PORT_MODE_IN, PORT_MODE_OUT
from wok import exit_codes

class MissingRequiredPorts(Exception):
	def __init__(self, missing_ports, mode):
		Exception.__init__(self, "Missing required {0} ports: {1}".format(mode, ", ".join(missing_ports)))

class MissingRequiredConf(Exception):
	def __init__(self, missing_keys):
		Exception.__init__(self, "Missing required configuration: {0}".format(", ".join(missing_keys)))

class PortsAccessor(object):
	"""Port accessor for backward compatibility"""
	def __init__(self, ports):
		self.__ports = ports

	def __call__(self, names, mode = [PORT_MODE_IN, PORT_MODE_OUT]):
		if names is None:
			ports = [port for port in self.__ports.values() if port.mode in mode]
		else:
			try:
				if isinstance(names, basestring):
					ports = [names]
				ports = [self.__ports[name] for name in names]
			except:
				raise Exception("Unknown port: {0}".format(e.args[0]))
		return ports

	def keys(self):
		return self.__ports.keys()

	def __len__(self):
		return len(self.__ports)

	def __getitem__(self, key):
		return self.__ports[key]

	def __iter__(self):
		return iter(self.__ports)

	def __contains__(self, key):
		return key in self.__ports

	def items(self):
		return self.__ports.items()

	def iteritems(self):
		return self.__ports.iteritems()

class Task(object):
	"""
	Processes a data partition of a module in a flow.
	"""

	__DEFAULT_SERIALIZER = "json"
	
	def __init__(self, start_func = None, required_conf = []):

		# Read data and configuration
		self.data = Config(required = required_conf)
		self.conf = self.data["conf"]
		del self.data["conf"]

		self._id = self.data["id"]

		# deprecated
		self._start_func = start_func

		self._main = None
		self._generators = []
		self._mappers = []
		self._before_main = None
		self._after_main = None

		self._start_time = 0
		self._end_time = self._start_time

		logger.initialize(self.conf.get("log"))
		self._log = self.logger()

		self.__initialize_ports()

		self.__ports_accessor = PortsAccessor(self._port_map)
		
		self.context = None
		
		#self._log.debug("Task:\nData: %s\nConfiguration: %s" % (self.data, self.conf))
	
	def __initialize_ports(self):
		self._port_map = {}
		if "ports" in self.data:
			for port_name, port_conf in self.data["ports"].iteritems():
				self._port_map[port_name] = PortFactory.create_port(port_name, port_conf)
		
	def __close_ports(self):
		for port in self._port_map.values():
			port.close()

	@staticmethod
	def __dot_product(ports):
		names = [port.name for port in ports]
		readers = [port.data.reader() for port in ports]
		sizes = [readers[i].size() for i in xrange(len(readers))]

		while sum(sizes) > 0:
			data = {}
			for i, reader in enumerate(readers):
				data[names[i]] = reader.read()
				sizes[i] = reader.size()
			yield data

	@staticmethod
	def __cross_product(ports):
		raise Exception("Cross product unimplemented")

	def __default_main(self):

		## Execute before main

		if self._before_main:
			self._log.debug("Processing before main ...")
			self._before_main()

		## Execute generators

		if self._generators:
			self._log.debug("Processing generators ...")

		for generator in self._generators:
			func, out_ports = generator

			self._log.debug("".join([func.__name__,
				"(out_ports=[", ", ".join([p.name for p in out_ports]), "])"]))

			params = {}
			for port in out_ports:
				params[port.name] = port

			func(**params)

		## Execute mappers

		if self._mappers:
			self._log.debug("Processing mappers ...")

		# initialize mappers
		mappers = []
		for mapper in self._mappers:
			func, in_ports, out_ports = mapper
			
			writers = [port.data.writer() for port in out_ports]

			mappers += [(func, in_ports, out_ports, writers)]

			self._log.debug("".join([func.__name__,
				"(in_ports=[", ", ".join([p.name for p in in_ports]),
				"], out_ports=[", ", ".join([p.name for p in out_ports]), "])"]))

		# determine input port data iteration strategy
		# currently only dot strategy supported
		port_data_strategy = self.__dot_product

		# process each port data iteration element
		ports = [port for port in self._port_map.values() if port.mode == PORT_MODE_IN]
		for data in port_data_strategy(ports):
			for mapper in mappers:
				func, in_ports, out_ports, writers = mapper

				params = {}
				for port in in_ports:
					params[port.name] = data[port.name]

				ret = func(**params)

				if not isinstance(ret, list):
					ret = [ret]

				if len(ret) != len(out_ports):
					port_list = ", ".join([p.name for p in out_ports])
					raise Exception("The number of values returned by '{0}' doesn't match the expected output ports: {1}".format(func.__name__, port_list))

				for i, writer in enumerate(writers):
					writer.write(ret[i])

		## Execute after main
		if self._after_main:
			self._log.debug("Processing after main ...")
			self._after_main()

		return 0

	def elapsed_time(self):
		return timedelta(seconds = time.time() - self._start_time)

	def logger(self, name = None):
		if name is None:
			name = self._id
		log = logger.get_logger(self.conf.get("log"), name)
		return log

	# deprecated, use ports() instead
	def port(self, name):
		if name not in self._port_map:
			raise Exception("Port '{0}' doesn't exist".format(name))

		return self._port_map[name]

	@property
	def ports(self):
		return self.__ports_accessor

	def check_conf(self, keys, exit_on_error = True):
		missing_keys = []
		for key in keys:
			if key not in self.conf:
				missing_keys += [key]

		if exit_on_error and len(missing_keys) > 0:
			raise MissingRequiredConf(missing_keys)

		return missing_keys

	# deprecated
	def check_ports(self, port_names, mode, exit_on_error = True):
		missing_ports = []
		for port_name in port_names:
			if port_name not in self._port_map or self._port_map[port_name].mode != mode:
				missing_ports += [port_name]

		if exit_on_error and len(missing_ports) > 0:
			raise MissingRequiredPorts(missing_ports, mode)

		return missing_ports

	# deprecated
	def check_in_ports(self, port_names, exit_on_error = True):
		return self.check_ports(port_names, PORT_MODE_IN, exit_on_error)

	# deprecated
	def check_out_ports(self, port_names, exit_on_error = True):
		return self.check_ports(port_names, PORT_MODE_OUT, exit_on_error)

	def start(self):
		try:
			import socket
			hostname = socket.gethostname()
		except:
			hostname = "unknown"

		self._log.debug("Task {0} started on host {1}".format(self._id, hostname))

		self._start_time = time.time()

		try:
			if self._main is not None:
				self._log.debug("Processing main ...")
				retcode = self._main()
				if retcode is None:
					retcode = 0
			elif self._start_func is not None:
				retcode = self._start_func(self)
				if retcode is None:
					retcode = 0
			else:
				retcode = self.__default_main()

			self._log.info("Elapsed time: {0}".format(self.elapsed_time()))
		except:
			self._log.exception("Exception on task {0}".format(self._id))
			retcode = exit_codes.TASK_EXCEPTION
		finally:
			self.__close_ports()

		exit(retcode)
		
	def set_main(self, f):
		self._main = f

	def main(self):
		"""
		A decorator that is used for specifying which is the task main function. Example::

			@task.main()
			def main():
				log = task.logger()
				log.info("Hello world")
		"""
		def decorator(f):
			self.set_main(f)
			return f

		return decorator

	def add_generator(self, generator_func, out_ports = None):
		"""Add a port data generator function"""
		self._generators += [(generator_func,
				self.ports(out_ports, PORT_MODE_OUT))]

	def generator(self, out_ports = None):
		"""
		A decorator that is used to define a function that will
		generate port output data. Example::

			@task.generator(out_ports = ["x", "sum"])
			def sum_n(x, sum):
				N = task.conf["N"]
				s = 0
				for i in xrange(N):
					x.write(i)
					sum.write(s)
					s += i
		"""
		def decorator(f):
			self.add_generator(f, out_ports)
			return f
		return decorator

	def add_mapper(self, mapper_func, in_ports = None, out_ports = None):
		"""Add a port data processing function"""
		self._mappers += [(mapper_func,
				self.ports(in_ports, PORT_MODE_IN),
				self.ports(out_ports, PORT_MODE_OUT))]

	def mapper(self, in_ports = None, out_ports = None):
		"""
		A decorator that is used to specify which is the function that will
		process each port input data. Example::

			@task.mapper(in_ports = ["in1", "in2"])
			def process(name, value):
				return name + " = " + str(value)
		"""
		def decorator(f):
			self.add_mapper(f, in_ports, out_ports)
			return f
		return decorator

	def set_before_main(self, f):
		"""Set the function that will be executed before starting the main function"""
		self._before_main = f

	def before_main(self):
		"""A decorator that is used to specify the function that will be
		executed before starting the main function"""
		def decorator(f):
			self.set_before_main(f)
			return f
		return decorator

	def set_after_main(self, f):
		"""Set the function that will be executed before starting the main function"""
		self._after_main = f

	def after_main(self):
		"""A decorator that is used to specify the function that will be
		executed after executing the main function"""
		def decorator(f):
			self.set_after_main(f)
			return f
		return decorator