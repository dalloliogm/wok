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

from wok.server.common import wok, Breadcrumb, BcLink

from flask import Module, request, session, redirect, url_for, \
	render_template, flash, current_app

monitoring = Module(__name__)

@monitoring.route('/')
def index():
	return render_template('monitoring.html')

@monitoring.route('/instance/<name>')
def instance(name):
	return render_template('monitoring/instance.html', name = name)