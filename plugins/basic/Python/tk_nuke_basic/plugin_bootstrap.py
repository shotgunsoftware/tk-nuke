# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import sys
import time

import nuke


def bootstrap(plugin_root_path):
    """
    Entry point for toolkit bootstrap in Nuke.

    Called by the basic/startup/menu.py file.

    :param str plugin_root_path: Path to the root folder of the plugin
    """

    # --- Import Core ---
    #
    # - If we are running the plugin built as a stand-alone unit,
    #   try to retrieve the path to sgtk core and add that to the pythonpath.
    #   When the plugin has been built, there is a sgtk_plugin_basic_nuke
    #   module which we can use to retrieve the location of core and add it
    #   to the pythonpath.
    # - If we are running toolkit as part of a larger zero config workflow
    #   and not from a standalone workflow, we are running the plugin code
    #   directly from the engine folder without a bundle cache and with this
    #   configuration, core already exists in the pythonpath.

    # now see if we are running stand alone or in situ
    try:
        from sgtk_plugin_basic_nuke import manifest
        running_stand_alone = True
    except ImportError:
        manifest = None
        running_stand_alone = False

    if running_stand_alone:
        # running stand alone. import core from the manifest's core path and
        # extract the plugin info from the manifest

        # Retrieve the Shotgun toolkit core included with the plug-in and
        # prepend its python package path to the python module search path.
        # this will allow us to import sgtk
        tk_core_python_path = manifest.get_sgtk_pythonpath(plugin_root_path)
        sys.path.insert(0, tk_core_python_path)

        # plugin info from the manifest
        plugin_id = manifest.plugin_id
        base_config = manifest.base_configuration

        # get the path to the built plugin's bundle cache
        bundle_cache = os.path.join(plugin_root_path, "bundle_cache")
    else:
        # running in situ as part of zero config. sgtk has already added sgtk
        # to the python path. need to extract the plugin info from info.yml

        # import the yaml parser
        from tank_vendor import yaml

        # build the path to the info.yml file
        plugin_info_yml = os.path.join(plugin_root_path, "info.yml")

        # open the yaml file and read the data
        with open(plugin_info_yml, "r") as plugin_info_fh:
            plugin_info = yaml.load(plugin_info_fh)

        base_config = plugin_info["base_configuration"]
        plugin_id = plugin_info["plugin_id"]

        # no bundle cache in in situ mode
        bundle_cache = None

    __launch_sgtk(base_config, plugin_id, bundle_cache)


def __launch_sgtk(base_config, plugin_id, bundle_cache):
    """
    Launches Toolkit and the engine.

    :param str base_config: Basic configuration to use for this plugin instance.
    :param str plugin_id: Plugin id of this plugin instance.
    :param str bundle_cache: Alternate bundle cache location. Can be ``None``.
    """

    # ---- now we have everything needed to bootstrap. finish initializing the
    #      manager and logger, authenticate, then bootstrap the engine.

    import sgtk

    # start logging to log file
    sgtk.LogManager().initialize_base_file_handler("tk-nuke")

    # get a logger for the plugin
    sgtk_logger = sgtk.LogManager.get_logger("plugin")
    sgtk_logger.debug("Booting up toolkit plugin.")

    sgtk_logger.debug("Executable: %s", sys.executable)
    sgtk_logger.debug("Studio environment set?: %s", nuke.env.get("studio"))
    sgtk_logger.debug("Hiero environment set?: %s", nuke.env.get("hiero"))

    try:
        # When the user is not yet authenticated, pop up the Shotgun login
        # dialog to get the user's credentials, otherwise, get the cached user's
        # credentials.
        user = sgtk.authentication.ShotgunAuthenticator().get_user()
    except sgtk.authentication.AuthenticationCancelled:
        # TODO: show a "Shotgun > Login" menu in nuke
        sgtk_logger.info("Shotgun login was cancelled by the user.")
        return

    # Create a boostrap manager for the logged in user with the plug-in
    # configuration data.
    toolkit_mgr = sgtk.bootstrap.ToolkitManager(user)

    toolkit_mgr.base_configuration = base_config
    toolkit_mgr.plugin_id = plugin_id

    # include the bundle cache as a fallback if supplied
    if bundle_cache:
        toolkit_mgr.bundle_cache_fallback_paths = [bundle_cache]

    # Retrieve the Shotgun entity type and id when they exist in the
    # environment. These are passed down through the app launcher when running
    # in zero config
    entity = toolkit_mgr.get_entity_from_environment()
    sgtk_logger.debug("Will launch the engine with entity: %s" % entity)

    bootstrapper = NukeBootstraper(toolkit_mgr, entity, sgtk_logger)
    bootstrapper.bootstrap()


class DeferredProgressTask(object):
    """
    This is a wrapper around Nuke's ``nuke.ProgressTask``. It basically allows to postpone the display
    of the widget to a later time, so the progress reporting appears only for tasks that are taking
    a very long time.
    """

    WAITING, RUNNING, COMPLETED = range(3)

    # Maximum amount of time the progress reporting can stay hidden before we need to show some
    # progress to the user.
    MAXIMUM_HIDDEN_TIME = 5

    def __init__(self):
        self._state = self.WAITING
        self._start_time = 0
        self._progress_task = None

    def start(self):
        """
        Starts the progress reporting. MAXIMUM_HIDDEN_TIME from now, the UI will
        be displayed.
        """
        self._start_time = time.time()
        self._state = self.RUNNING

    def done(self):
        """
        Tells the progress reporter that it is done. This will dismiss the widget from the UI.
        """
        self._state = self.COMPLETED
        self._progress_task = None

    def report_progress(self, percentage, message):
        """
        Reports progress in the UI, but only if MAXIMUM_HIDDEN_TIME has elapsed.

        :param float percentage: Number to display in the UI for progress.
        :param str message: Message to display.
        """
        # Check the progress task reported widget, but only if it is required yet.
        progress_task = self._get_progress_task()
        if progress_task is None:
            return

        if progress_task.isCancelled():
            raise Exception("Toolkit initialization was cancelled by the user.")

        progress_task.setMessage(message)
        progress_task.setProgress(percentage)

        if progress_task.isCancelled():
            raise Exception("User cancelled the Toolkit startup process...")

    def _get_progress_task(self):
        """
        Returns a progress task object if enough time has elapsed.
        """

        # If we've started reporting progress already, just return the progress reporter.
        if self._progress_task:
            return self._progress_task

        # If we're waiting for the progress reporting to start, do nothing.
        if self._state == self.WAITING:
            return None

        # If we're currently running. (someone invoked start())
        if self._state == self.RUNNING:
            # If more than MAXIMUM_HIDDEN_TIME seconds have passed since we started, create the widget
            # and return it.
            elapsed = time.time() - self._start_time
            if elapsed > self.MAXIMUM_HIDDEN_TIME:
                self._progress_task = nuke.ProgressTask("Initializing Toolkit...")
                return self._progress_task
            else:
                # Not enough time has elapsed, widget will not be available.
                return None

        # State is completed, we're done, nothing to report.
        return None


class NukeBootstraper(object):
    """
    Glue between the ToolkitManager and the DCC. Makes sure progress is reported to the GUI.
    """

    def __init__(self, toolkit_mgr, entity, logger):
        """
        :param toolkit_mgr: ToolkitManager instance used for bootstrapping.
        :param entity: Entity for which we want to bootstrap.
        :param logger: Logger to use while progress reporting.
        """
        self._progress_task = DeferredProgressTask()
        self._logger = logger
        self._entity = entity
        self._toolkit_mgr = toolkit_mgr
        self._is_bootstrapping = False

    def bootstrap(self):
        """
        Starts the bootstrap process.
        """
        # Nuke doesn't like us starting a thread while it is still initializing. Nuke 7 is fine, so
        # is Nuke Studio 10. However, Nuke 10 wants us to wait. nuke.executeInMainThread or
        # nukescripts.utils.executeDeferred don't seem to help, so we wait for the first node to be
        # created. As for Nuke Studio 9? It doesn't like the asynchronous bootstrap, so we'll have
        # to start synchronously.
        if nuke.env.get("studio") and nuke.env.get("NukeVersionMajor") < 10:
            self._toolkit_mgr.bootstrap_engine(
                os.environ.get("SHOTGUN_ENGINE", "tk-nuke"),
                self._entity
            )
        else:
            nuke.addOnCreate(self._bootstrap)

    def _bootstrap(self):
        """
        Invoked when Nuke is done with building it's UI. This will launch the bootstrap process
        and start reporting progress.
        """
        # Paranoia. This is in case something goes wrong with the removeOnCreate call. I don't know what
        # could go wrong, but I don't want the risk or rebootstrapping every single time someone adds a
        # node. That would be really, really bad.
        if self._is_bootstrapping:
            self._logger.warning("Unexpected call to NukeBoostrapper._bootstrap.")
            return

        # Unregister from the node event, we're bootstrapping now.
        self._is_bootstrapping = True
        nuke.removeOnCreate(self._bootstrap)

        self._toolkit_mgr.progress_callback = self._report
        self._toolkit_mgr.bootstrap_engine_async(
            os.environ.get("SHOTGUN_ENGINE", "tk-nuke"),
            self._entity, lambda engine: self._on_finish(), self._on_failure
        )
        self._progress_task.start()

        # Contrary to other engines, do not clear the SHOTGUN_ENGINE environment variable.
        # Nuke spawns a new process when doing a File->Open or File->New, which means our
        # plug-in needs to be able to bootstrap a second time.

    def _report(self, progress_value, message):
        """
        Called by the ToolkitManager to report progress. It will go to the logs and the ProgressTask
        widget.

        :param float progress_value: Between 0 and 1. Indicates progress.
        :param str message: Current message to display.
        """

        # Report in the Toolkit Log.
        percentage = int(progress_value * 100)
        self._logger.debug("[%s] - %s", percentage, message)
        self._progress_task.report_progress(percentage, message)
        print message

    def _on_finish(self):
        """
        Called after bootstrap (success or failure) to cleanup resources.
        """
        # At this point we are guaranteed that bootstrapped is finished, so we can dismiss progress
        # reporting.
        self._progress_task.done()

    def _on_failure(self, phase, exception):
        """
        Called when something went wrong during bootstrap.

        :param phase: Phase which went wrong.
        :param exception: Exception that was raised.
        """
        try:
            nuke.error("Initialization failed: %s" % str(exception))
        finally:
            self._on_finish()
