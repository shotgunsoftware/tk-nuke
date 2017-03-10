import inspect
import os
import sys


def plugin_startup():

    current_file_path = os.path.abspath(
        inspect.getsourcefile(lambda: 0)
    )

    plugin_root_path = os.path.dirname(current_file_path)

    # the plugin python path will be just below the root level. add it to
    # sys.path
    plugin_python_path = os.path.join(plugin_root_path, "python")
    sys.path.insert(0, plugin_python_path)

    # now that the path is there, we can import the plugin bootstrap logic
    try:
        from tk_nuke_basic import plugin_bootstrap
        plugin_bootstrap.bootstrap(plugin_root_path, os.environ.get("SGTK_ENGINE"), has_gui=True)
    except Exception, e:
        import traceback
        stack_trace = traceback.format_exc()

        message = "Shotgun Toolkit Error: %s" % (e,)
        details = "Error stack trace:\n\n%s" % (stack_trace)

        import nuke
        nuke.error(message)
        nuke.error(details)


plugin_startup()
