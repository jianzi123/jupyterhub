"""User handlers"""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json
import pwd
import crypt
import os
from subprocess import Popen, PIPE

from tornado import gen, web

from .. import orm
from ..utils import admin_only
from .base import APIHandler
from os.path import exists
from os.path import isfile

class SelfAPIHandler(APIHandler):
    """Return the authenticated user's model
    
    Based on the authentication info. Acts as a 'whoami' for auth tokens.
    """
    @web.authenticated
    def get(self):
        user = self.get_current_user()
        if user is None:
            # whoami can be accessed via oauth token
            user = self.get_current_user_oauth_token()
        if user is None:
            raise web.HTTPError(403)
        self.write(json.dumps(self.user_model(user)))

class UserListAPIHandler(APIHandler):
    @admin_only
    def get(self):
        users = [ self._user_from_orm(u) for u in self.db.query(orm.User) ]
        data = [ self.user_model(u) for u in users ]
        self.write(json.dumps(data))
    
    @admin_only
    @gen.coroutine
    def post(self):
        data = self.get_json_body()
        self.log.info('add user data', data.get('usernames'))
        if not data or not isinstance(data, dict) or not data.get('usernames'):
            raise web.HTTPError(400, "Must specify at least one user to create")
        
        usernames = data.pop('usernames')
        self._check_user_model(data)
        # admin is set for all users
        # to create admin and non-admin users requires at least two API requests
        admin = data.get('admin', False)
        
        to_create = []
        invalid_names = []
        for name in usernames:
            try:
                info = pwd.getpwnam(name)
                if info is not None:
                    continue
            except KeyError:
                pass
            name = self.authenticator.normalize_username(name)
            if not self.authenticator.validate_username(name):
                invalid_names.append(name)
                continue
            user = self.find_user(name)
            self.log.info(name)
            if user is not None:
                self.log.warning("User %s already exists" % name)
            else:
                to_create.append(name)
        
        if invalid_names:
            if len(invalid_names) == 1:
                msg = "Invalid username: %s" % invalid_names[0]
            else:
                msg = "Invalid usernames: %s" % ', '.join(invalid_names)
            raise web.HTTPError(400, msg)
        
        if not to_create:
            raise web.HTTPError(400, "All %i users already exist" % len(usernames))
        
        created = []
        for name in to_create:
            user = self.user_from_username(name)
            self.log.info('create: %s', name)
            if admin:
                user.admin = True
                self.db.commit()
                info = orm.User_info.create(self.db, name)
                if info is None:
                    raise web.HTTPError(400, "Failed to create user %s" % (name))
            try:
                yield gen.maybe_future(self.authenticator.add_user(user))


            except Exception as e:
                self.log.error("Failed to create user: %s" % name, exc_info=True)
                del self.users[user]
                raise web.HTTPError(400, "Failed to create user %s: %s" % (name, str(e)))
            else:
                info = orm.User_info.create(self.db, name)
                if info is None:
                    raise web.HTTPError(400, "Failed to create user %s" % (name))
                else:
                    created.append(user)
            data_dir = info.data_dir
            if data_dir is None or data_dir == '':
                self.log.warning('data_dir is empty.')
            else:
                cmd = 'mkdir -p -m 777 ' + data_dir
                if os.system(cmd) != 0 :
                    raise web.HTTPError(400, "Failed to create data dir %s." % (data_dir))
        self.write(json.dumps([ self.user_model(u) for u in created ]))
        self.set_status(201)


def admin_or_self(method):
    """Decorator for restricting access to either the target user or admin"""
    def m(self, name, *args, **kwargs):
        current = self.get_current_user()
        if current is None:
            raise web.HTTPError(403)
        if not (current.name == name or current.admin):
            raise web.HTTPError(403)
        
        # raise 404 if not found
        if not self.find_user(name):
            raise web.HTTPError(404)
        return method(self, name, *args, **kwargs)
    return m

class UserAPIHandler(APIHandler):
    
    @admin_or_self
    def get(self, name):
        user = self.find_user(name)
        self.write(json.dumps(self.user_model(user)))
    
    @admin_only
    @gen.coroutine
    def post(self, name):
        data = self.get_json_body()
        user = self.find_user(name)
        if user is not None:
            raise web.HTTPError(400, "User %s already exists" % name)
        
        user = self.user_from_username(name)
        if data:
            self._check_user_model(data)
            if 'admin' in data:
                user.admin = data['admin']
                self.db.commit()
        
        try:
            yield gen.maybe_future(self.authenticator.add_user(user))
        except Exception:
            self.log.error("Failed to create user: %s" % name, exc_info=True)
            # remove from registry
            del self.users[user]
            raise web.HTTPError(400, "Failed to create user: %s" % name)
        
        self.write(json.dumps(self.user_model(user)))
        self.set_status(201)
    
    @admin_only
    @gen.coroutine
    def delete(self, name):
        user = self.find_user(name)
        if user is None:
            raise web.HTTPError(404)
        if user.name == self.get_current_user().name:
            raise web.HTTPError(400, "Cannot delete yourself!")
        if user.stop_pending:
            raise web.HTTPError(400, "%s's server is in the process of stopping, please wait." % name)
        if user.running:
            yield self.stop_single_user(user)
            if user.stop_pending:
                raise web.HTTPError(400, "%s's server is in the process of stopping, please wait." % name)
        u = orm.User.find(self.db, name)
        if u is not None:
            info = orm.User_info.find(self.db, name)
            if info is not None:
                # orm.User_info.remove(info)
                self.db.delete(info)
                self.db.commit()
        yield gen.maybe_future(self.authenticator.delete_user(user))
        # remove from registry
        del self.users[user]
        
        self.set_status(204)
    
    @admin_only
    def patch(self, name):
        user = self.find_user(name)
        if user is None:
            raise web.HTTPError(404)
        data = self.get_json_body()
        # remove the check to add user_info
        # self._check_user_model(data)
        if 'name' in data and data['name'] != name:
            # check if the new name is already taken inside db
            if self.find_user(data['name']):
                raise web.HTTPError(400, "User %s already exists, username must be unique" % data['name'])
        # for key, value in data.items():
        #     setattr(user, key, value)
        setattr(user, 'admin', data['admin'])
        setattr(user, 'name', data['name'])
        info = orm.User_info.find(self.db, name)
        if info is None:
            raise web.HTTPError(400, "user: %s not exist in db." % name)
        self.log.info(info)
        o_home  = info.home
        o_data  = info.data_dir
        o_shell = info.shell
        cmd = []
        if o_home != data['home']:
            if exists(data['home']):
                raise web.HTTPError(500, " %s dir exist, please pich others." % data['home'])
            else:
                cmd.append('usermod -md ' + data['home'] + ' ' + name)
                # self.log.info(cmd)
                # if os.system(cmd) != 0 :
                #     raise web.HTTPError(500, " changing home dir to %s failed." % data['home'])
        self.log.info('%s; %s', o_data, data['data'])
        if o_data != data['data']:
            if exists(data['data']):
                raise web.HTTPError(500, " %s dir exist, please pich others." % data['data'])
            else :
                if exists(o_data) == False:
                    cmd.append('mkdir -p -m 777 ' + data['data'])
                    # self.log.info('%s', cmd)
                    # if os.system(cmd) != 0:
                    #     raise web.HTTPError(500, " create dir %s failed." % data['data'])
                else:
                    cmd.append('mv ' + o_data + ' ' + data['data'])
                    # self.log.info('%s', cmd)
                    # if os.system(cmd) != 0 :
                    #     raise web.HTTPError(500, " changing dir %s to %s failed." % o_data, data['data'])
        if o_shell != data['shell']:
            if isfile(data['shell']) == False:
                raise web.HTTPError(500, " %s is not exist, please repick someone." % data['shell'])
            else:
                cmd.append('usermod -s ' + data['shell'] + ' ' + name)
                # self.log.info(cmd)
                # if os.system(cmd) != 0 :
                #     raise web.HTTPError(500, " changing shell to %s failed." % data['shell'])
        for tmp in cmd:
            if os.system(tmp) != 0 :
                raise web.HTTPError(500, " exec command %s failed." % tmp)
        setattr(info, 'home', data['home'])
        setattr(info, 'data_dir', data['data'])
        setattr(info, 'shell', data['shell'])
        self.db.commit()
        self.write(json.dumps(self.user_model(user)))
        

class UserServerAPIHandler(APIHandler):
    """Create and delete single-user servers
    
    This handler should be used when c.JupyterHub.allow_named_servers = False
    """
    @gen.coroutine
    @admin_or_self
    def post(self, name):
        user = self.find_user(name)
        if user.running:
            # include notify, so that a server that died is noticed immediately
            state = yield user.spawner.poll_and_notify()
            if state is None:
                raise web.HTTPError(400, "%s's server is already running" % name)

        options = self.get_json_body()
        yield self.spawn_single_user(user, options=options)
        status = 202 if user.spawn_pending else 201
        self.set_status(status)

    @gen.coroutine
    @admin_or_self
    def delete(self, name):
        user = self.find_user(name)
        if user.stop_pending:
            self.set_status(202)
            return
        if not user.running:
            raise web.HTTPError(400, "%s's server is not running" % name)
        # include notify, so that a server that died is noticed immediately
        status = yield user.spawner.poll_and_notify()
        if status is not None:
            raise web.HTTPError(400, "%s's server is not running" % name)
        yield self.stop_single_user(user)
        status = 202 if user.stop_pending else 204
        self.set_status(status)


class UserCreateNamedServerAPIHandler(APIHandler):
    """Create a named single-user server
    
    This handler should be used when c.JupyterHub.allow_named_servers = True
    """
    @gen.coroutine
    @admin_or_self
    def post(self, name):
        user = self.find_user(name)
        if user is None:
            raise web.HTTPError(404, "No such user %r" % name)
        if user.running:
            # include notify, so that a server that died is noticed immediately
            state = yield user.spawner.poll_and_notify()
            if state is None:
                raise web.HTTPError(400, "%s's server is already running" % name)

        options = self.get_json_body()
        yield self.spawn_single_user(user, options=options)
        status = 202 if user.spawn_pending else 201
        self.set_status(status)


class UserDeleteNamedServerAPIHandler(APIHandler):
    """Delete a named single-user server
    
    Expect a server_name inside the url /user/:user/servers/:server_name
    
    This handler should be used when c.JupyterHub.allow_named_servers = True
    """
    @gen.coroutine
    @admin_or_self
    def delete(self, name, server_name):
        user = self.find_user(name)
        if user.stop_pending:
            self.set_status(202)
            return
        if not user.running:
            raise web.HTTPError(400, "%s's server is not running" % name)
        # include notify, so that a server that died is noticed immediately
        status = yield user.spawner.poll_and_notify()
        if status is not None:
            raise web.HTTPError(400, "%s's server is not running" % name)
        yield self.stop_single_user(user)
        status = 202 if user.stop_pending else 204
        self.set_status(status)

class UserAdminAccessAPIHandler(APIHandler):
    """Grant admins access to single-user servers
    
    This handler sets the necessary cookie for an admin to login to a single-user server.
    """
    @admin_only
    def post(self, name):
        self.log.warning("Deprecated in JupyterHub 0.8."
            " Admin access API is not needed now that we use OAuth.")
        current = self.get_current_user()
        self.log.warning("Admin user %s has requested access to %s's server",
            current.name, name,
        )
        if not self.settings.get('admin_access', False):
            raise web.HTTPError(403, "admin access to user servers disabled")
        user = self.find_user(name)
        if user is None:
            raise web.HTTPError(404)
        if not user.running:
            raise web.HTTPError(400, "%s's server is not running" % name)

class UserPwdAPIHandler(APIHandler):
    def get(self, name):
        if not  name:
            raise web.HTTPError(400, "user: %s is empty." % name)
        info = orm.User_info.find(self.db, name)
        # current = pwd.getpwnam(name)
        # if current is None:
        #     raise  web.HTTPError(400, "user: %s not exist." % name)
        # data = {
        #     'name': current.pw_name,
        #     'dir': current.pw_dir,
        #     'shell': current.pw_shell,
        # }
        if info is None:
            raise web.HTTPError(400, "user: %s not exist in db." % name)
        data = {
            'name': name,
            'dir': info.data_dir,
            'shell': info.shell,
            'home': info.home,
        }
        self.write(json.dumps(data))

    @admin_only
    def post(self, name):
        pass

default_handlers = [
    (r"/api/user", SelfAPIHandler),
    (r"/api/users", UserListAPIHandler),
    (r"/api/users/([^/]+)", UserAPIHandler),
    (r"/api/users/([^/]+)/server", UserServerAPIHandler),
    (r"/api/users/([^/]+)/servers", UserCreateNamedServerAPIHandler),
    (r"/api/users/([^/]+)/servers/([^/]+)", UserDeleteNamedServerAPIHandler),
    (r"/api/users/([^/]+)/admin-access", UserAdminAccessAPIHandler),
    (r"/api/users/pwd/([^/]+)", UserPwdAPIHandler),
]
