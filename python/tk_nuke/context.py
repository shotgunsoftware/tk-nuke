# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Callbacks to manage the engine when a new file is loaded in tank.

"""
import os
import sys
import copy

import nuke
import tank


class ContextSwitcherBase(object):
    INIT_CONTEXT = None

    def __init__(self, engine):
        self._engine = engine
        self._context_cache = {}
        self.register_events()

    ##########################################################################
    # properties

    @property
    def engine(self):
        if not self._engine:
            self._engine = tank.platform.current_engine()
        return self._engine

    @property
    def context(self):
        if self.engine:
            self._context = self.engine.context
        return self._context

    @property
    def init_context(self):
        if not ContextSwitcherBase.INIT_CONTEXT:
            ContextSwitcherBase.INIT_CONTEXT = self.engine.context
        return ContextSwitcherBase.INIT_CONTEXT

    ##########################################################################
    # private

    def _get_new_context(self, script_path):
        context = self._context_cache.get(script_path)

        if context:
            return context

        try:
            context = self._get_context_from_script(script_path)
            if context:
                self._context_cache[script_path] = context
                return context
            else:
                raise tank.TankError(
                    'Toolkit could not determine the context associated with this script.'
                )
        except Exception, e:
            self.engine.menu_generator.create_tank_disabled_menu(e)
            self.engine.log_debug(e)

        return None

    def _get_context_from_script(self, script):
        # create new tank instance in case the script is located under another
        # project
        tk = tank.tank_from_path(script)
        context = tk.context_from_path(script,
                                       previous_context=self.engine.context)
        if context.project is None:
            raise tank.TankError("The Nukestudio engine needs at least a project "
                                 "in the context in order to start! Your context: %s"
                                 % context)
        else:
            return context

    def _change_context(self, new_context):
        """
        Checks the the tank engine should be
        """
        # try to create new engine
        try:
            tank.platform.change_context(new_context)
        except tank.TankEngineInitError, e:
            # context was not sufficient! - disable tank!
            self.engine.menu_generator.create_tank_disabled_menu(e)

    ##########################################################################
    # public

    def destroy(self):
        self.unregister_events()

    def register_events(self, unregister=False):
        pass

    def unregister_events(self):
        pass


class NukeContextSwitcher(ContextSwitcherBase):

    """
    Make sure that we have callbacks tracking context state changes for New Comp
    and Open Comp calls
    """

    def __init__(self, engine):
        super(NukeContextSwitcher, self).__init__(engine)
        self._event_desc = [{'add': nuke.addOnCreate,
                             'remove': nuke.removeOnCreate,
                             'registrar': nuke.callbacks.onCreates,
                             'function': self._tank_startup_node_callback},
                            {'add': nuke.addOnScriptSave,
                             'remove': nuke.removeOnScriptSave,
                             'registrar': nuke.callbacks.onScriptSaves,
                             'function': self._tank_on_save_callback}]

    ##########################################################################
    # private

    def _check_if_registered(self, func, registrar):
        """
        checks if a callback is already registered with nuke or not
        the test is made by comparing the name of the functions
        see: http://docs.thefoundry.co.uk/nuke/90/pythondevguide/callbacks.html
        """
        for nodeClass_category in registrar.values():
            for (function, args, kwargs, nodeClass) in nodeClass_category:
                if func.__name__ == function.__name__:
                    return True
        return False

    def _tank_on_save_callback(self):
        """
        Callback that fires every time a file is saved.

        Carefully manage exceptions here so that a bug in Tank never
        interrupts the normal workflows in Nuke.
        """
        try:
            # this file could be in another project altogether, so create a new Tank
            # API instance.

            # get the new file name
            file_name = nuke.root().name()
            try:
                tk = tank.tank_from_path(file_name)
            except tank.TankError, e:
                self.engine.menu_generator.create_tank_disabled_menu(e)
                return

            # and now extract a new context based on the file
            new_ctx = tk.context_from_path(file_name,
                                           previous_context=self.context)

            # now restart the engine with the new context
            self._restart_engine(tk, new_ctx)
        except Exception:
            self.engine.menu_generator.create_tank_error_menu()

    def _tank_startup_node_callback(self):
        """
        Callback that fires every time a node gets created.

        Carefully manage exceptions here so that a bug in Tank never
        interrupts the normal workflows in Nuke.
        """
        try:
            # look for the root node - this is created only when a new or existing
            # file is opened.
            if nuke.thisNode() != nuke.root():
                return

            if nuke.root().name() == "Root":
                # file->new
                # base it on the context we 'inherited' from the prev session
                # get the context from the previous session - this is helpful if
                # user does file->new
                tk = tank.Tank(self._init_project_root)

                if self.init_context:
                    new_ctx = self.init_context
                else:
                    new_ctx = tk.context_empty()
            else:
                # file->open
                file_name = nuke.root().name()
                try:
                    tk = tank.tank_from_path(file_name)
                except tank.TankError, e:
                    self.engine.menu_generator.create_tank_disabled_menu(e)
                    return

                new_ctx = tk.context_from_path(file_name,
                                               previous_context=self.context)

            # now restart the engine with the new context
            self._restart_engine(tk, new_ctx)
        except Exception:
            self.engine.menu_generator.create_tank_error_menu()

    ##########################################################################
    # public overrides

    def register_events(self, unregister=False):

        for func_desc in self._event_desc:
            # this is the variable that gets a dict of currently registered
            # callbacks
            registrar = func_desc.get('registrar')
            # the function we wish to un-/register
            function = func_desc.get('function')
            # the function used to register the callback
            add = func_desc.get('add')
            # the function used to unregister the callback
            remove = func_desc.get('remove')

            # select the function to use according to the unregister flag
            reg_func = [add, remove][unregister]
            # check if the call back is already registered or not
            found = self._check_if_registered(function, registrar)

            # only execute the register if the callback is not found in the registrar
            # or unregister if it is
            if unregister == found:
                reg_func(function)

    def unregister_events(self):
        self.register_events(unregister=True)


class StudioContextSwitcher(NukeContextSwitcher):
    def __init__(self, engine):
        super(StudioContextSwitcher, self).__init__(engine)

        # the last context on nukestudio we were in. This gets derived from the
        # event.focusInNuke property which is True if the the current focus is
        # in a Nuke context and False otherwise
        self._current_studio_context = False

    ##########################################################################
    # properties

    @property
    def current_studio_context(self):
        return ['Hiero', 'Nuke'][self._current_studio_context]

    ##########################################################################
    # private

    def _eventHandler(self, event):
        """
        Event handler for context switch event in nukestudio. Switching from Hiero
        to Nuke
        """
        focusInNuke = event.focusInNuke
        # testing if we actually changed context or if the event got fired without
        # the user switching to the node graph. early exit if it's still the
        # same context
        if self._current_studio_context == focusInNuke:
            return

        # set the current context to be remembered for the next context
        # change
        self._current_studio_context = focusInNuke

        if focusInNuke:
            # we switched from hiero to a nuke node graph
            try:
                script_path = nuke.scriptName()
            except:
                script_path = None

            if script_path:
                # switched to nuke with a script open. We have a path and could try
                # to figure out the tank context from that

                ###########################################################
                # here we would switch the context of the engine and apps to
                # reflect the context of the open script. A menu rebuild
                # should also be triggered
                new_context = self._get_new_context(script_path)

                if new_context is not None and new_context != self.engine.context:
                    self._change_context(new_context)
            else:
                # there is no script open in the nuke node graph. Empty
                # session so we won't switch to a new context
                # although we should rebuild the menu to reflect the nuke
                # context
                self.engine.menu_generator.create_tank_disabled_menu()
        else:
            self._change_context(self.init_context)

    ##########################################################################
    # public overrides

    def register_events(self, unregister=False):
        import hiero.core

        # switch between the function to register/unregister the event interest
        reg_func = [
            hiero.core.events.registerInterest,
            hiero.core.events.unregisterInterest,
        ][unregister]

        # event for context switching from hiero to nuke
        reg_func(
            hiero.core.events.EventType.kContextChanged,
            self._eventHandler,
        )

        super(StudioContextSwitcher, self).register_events(unregister)

    def unregister_events(self):
        self.register_events(unregister=True)
