# ******************************************************************
# Copyright 2009, Universitat Pompeu Fabra
#
# Licensed under the Non-Profit Open Software License version 3.0
# ******************************************************************

from wok.server.common import wok, Breadcrumb, BcLink

from flask import Module, request, session, redirect, url_for, \
	render_template, flash, current_app

home = Module(__name__)

@home.route('/')
def index():
	return render_template('index.html')