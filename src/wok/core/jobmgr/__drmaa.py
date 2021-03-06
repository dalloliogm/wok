###############################################################################
#
#    Copyright 2009-2011, Universitat Pompeu Fabra
#
#    This file is part of Wok.
#
#    Wok is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Wok is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses
#
###############################################################################

import drmaa
import os
import shutil
from stat import S_IRUSR, S_IWUSR, S_IXUSR, S_IRGRP, S_IWGRP, S_IXGRP, S_IROTH, S_IWOTH, S_IXOTH

from wok import logger
from wok.scheduler import JobScheduler
from wok.launcher.factory import create_launcher
from wok import exit_codes

class DrmaaJobScheduler(JobScheduler):
	def __init__(self, conf):
		JobScheduler.__init__(self, conf)
		
		mf = conf.missing_fields(["__work_path"])
		if len(mf) > 0:
			raise Exception("Missing configuration: [%s]" % ", ".join(mf))

		self._log = logger.get_logger(conf.get("log"), "drmaa")

		self._work_path = conf["__work_path"]
		self._shell_path = os.path.join(self._work_path, "sh")
		if not os.path.exists(self._shell_path):
			os.makedirs(self._shell_path)

		self._working_directory = conf.get("working_directory", None)
		
		self._autorm_sh = conf.get("auto_remove.sh", True, dtype=bool)

		self._waiting = []
		self._jobs = {}

	def start(self):
		self._log.info("Starting DRMAA scheduler ...")

		self._session = drmaa.Session()
		self._session.initialize()

		sb = ["DRMAA initialized:\n"]
		sb += ["\tSupported contact strings: %s\n" % self._session.contact]
		sb += ["\tSupported DRM systems: %s\n" % self._session.drmsInfo]
		sb += ["\tSupported DRMAA implementations: %s\n" % self._session.drmaaImplementation]
		sb += ["\tVersion %s" % str(self._session.version)]
		self._log.debug("".join(sb))

	def clean(self):
		for path in [self._shell_path]:
			if os.path.exists(path):
				self._log.debug(path)
				shutil.rmtree(path)
			os.makedirs(path)

	def _create_shell(self, task, shell, cmd, env):
		if shell is None:
			shell = "/bin/bash"

		shell_script = os.path.join(self._shell_path, "%s.sh" % task["id"])

		sb = []
		for k,v in env.items():
			sb += ["export %s=%s" % (k, v)]
		env_def = "\n".join(sb)

		f = open(shell_script, "w")
		f.write("""#!%s

%s $*
""" % (shell, cmd))
		#f.write("#!%s\n" % shell)
		#f.write("\n%s $*\n" % cmd)
		f.close()
		os.chmod(shell_script, S_IRUSR | S_IWUSR | S_IXUSR | S_IRGRP | S_IWGRP | S_IXGRP | S_IROTH | S_IWOTH | S_IXOTH)
		return shell_script

	def submit(self, task):
		execution = task["exec"]
		launcher_name = execution.get("launcher", None)
		if "conf" in execution:
			exec_conf = execution["conf"]
		else:
			exec_conf = execution.create_element()

		task_conf = task["conf"]
		launcher_conf_key = "wok.launchers.%s" % launcher_name
		if launcher_conf_key in task_conf:
			launcher_conf = task_conf[launcher_conf_key]
		else:
			launcher_conf = task_conf.create_element()

		launcher = create_launcher(launcher_name, launcher_conf)

		shell, cmd, args, env = launcher.template(exec_conf, task)

		shell_cmd = self._create_shell(task, shell, cmd, env)

		job_name = "-".join([task_conf["wok.__instance.name"], task["id"]])

		native_specification = task_conf.get("wok.schedulers.drmaa.native_specification")

		#output_path = os.path.join(self._output_path, "%s.txt" % task["id"])
		output_path = task["job/output_path"]
		
		jt = self._session.createJobTemplate()
		jt.jobName = job_name
		jt.remoteCommand = shell_cmd
		jt.args = args
		jt.jobEnvironment = env
		jt.outputPath = ":" + output_path
		jt.joinFiles = True
		if self._working_directory is not None:
			jt.workingDirectory = self._working_directory
		if native_specification is not None:
			jt.nativeSpecification = native_specification
		
		sb = ["%s %s" % (cmd, " ".join(args))]
		if len(env) > 0:
			sb += ["\n"]
			for k, v in env.iteritems():
				sb += ["\t%s=%s" % (k, v)]
		self._log.debug("".join(sb))
		
		jobid = self._session.runJob(jt)
		self._waiting += [jobid]
		self._jobs[jobid] = {
			"task" : task,
			"sh_path" : shell_cmd,
			"output_path" : output_path
		}
		
		task["job"] = job_conf = task.create_element()
		job_conf["id"] = jobid
		job_conf["job_name"] = job_name
		job_conf["command"] = cmd
		job_conf["args"] = job_conf.create_list(args)
		job_conf["env"] = job_conf.create_element(env)
		job_conf["output_path"] = output_path
		if self._working_directory is not None:
			job_conf["working_dir"] = self._working_directory
		if native_specification is not None:
			job_conf["native_specification"] = native_specification
		
		self._log.info("Task %s submited as job %s." % (task["id"], jobid))
		
		self._session.deleteJobTemplate(jt)
	
	def wait(self, timeout=None):
		tasks = []
		
		self._session.synchronize(self._waiting, drmaa.Session.TIMEOUT_WAIT_FOREVER, False)
		for jobid in self._waiting:
			job = self._jobs[jobid]
			task = job["task"]
			tasks += [task]

			try:
				ret = self._session.wait(jobid, drmaa.Session.TIMEOUT_WAIT_FOREVER)
			
				sh_path = job["sh_path"]
				output_path = job["output_path"]
				del self._jobs[jobid]

				if self._autorm_sh:
					os.remove(sh_path)

				exit_code = exit_codes.UNKNOWN
				sb = ["Task %s (job %s)" % (task["id"], jobid)]
				if ret.wasAborted:
					sb += [" was aborted"]
					if ret.hasCoreDump:
						sb += [" with core dump"]
				elif ret.hasExited:
					sb += [" has exited with code %s" % ret.exitStatus]
					exit_code = ret.exitStatus
				elif ret.hasSignal:
					sb += [" got signal %s" % ret.terminatedSignal]
				else:
					sb += [" has finished unexpectedly"]

				exit_msg = "".join(sb)
				self._log.debug(exit_msg)

				task["job/exit/code"] = exit_code
				task["job/exit/message"] = exit_msg
			except Exception as e:
				self._log.exception(e)
				task["job/exit/code"] = exit_codes.EXCEPTION_WAITING
				task["job/exit/message"] = "There was an exception while waiting for the job to finish: %s" % e
			
		self._waiting = []
		
		return tasks

	def finished(self):
		return len(self._waiting) == 0
	
	def stop(self):
		self._session.exit()

