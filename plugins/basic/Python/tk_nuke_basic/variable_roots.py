import base64

import sgtk
import nuke

backup_knob_suffix = "_tk_backup_prop"


def get_all_nodes():
    """
    Returns all nodes in the current context, including the ones inside group nodes.
    The context is the scene unless we are inside a group node using the context manager
    """
    for node in nuke.allNodes():
        # Traverse the inner nodes of a  group
        if isinstance(node, nuke.Group):
            with node:
                for inner_node in get_all_nodes():
                    yield inner_node
        yield node


def get_file_knobs(node):
    """
    Retruns all knobs of type "File_Knob" on the node
    """
    for knob_name, knob in node.knobs().items():
        if isinstance(knob, nuke.File_Knob):
            yield knob


def to_backup_knob_name(name):
    return name + backup_knob_suffix


def to_real_knob_name(name):
    return name.replace(backup_knob_suffix, "")


def is_backup_knob(knob_name):
    return knob_name.endswith(backup_knob_suffix)


# Encode and decode values when storing them so nuke's tcl engine doesn't try to evaluate the env vars
def encode_backup_value(value):
    return base64.b64encode(value)


def decode_backup_value(value):
    return base64.b64decode(value)


def update_backup_knob(node, knob_name, value):
    """
    Creates/updates a backup knob that corresponds to the given knob and stores the
    encoded version of the given value in the knob
    """
    backup_knob_name = to_backup_knob_name(knob_name)
    backup_knob = node.knob(backup_knob_name)

    # If the knob doesn't exist, create it
    if not backup_knob:
        backup_knob = nuke.String_Knob(backup_knob_name)
        backup_knob.setEnabled(False)
        node.addKnob(backup_knob)

    backup_knob.setValue(encode_backup_value(value))


def remove_backup_knob(node, knob_name):
    """
    Removes the backup knob that corresponds to knob_name if one exists
    """
    backup_knob_name = to_backup_knob_name(knob_name)
    backup_knob = node.knob(backup_knob_name)

    if backup_knob:
        node.removeKnob(backup_knob)


def script_save_callback():
    """
    Callback to store the variable root information on all nodes in the scene
    """
    import sgtk

    engine = sgtk.platform.util.current_engine()
    for node in get_all_nodes():
        for knob in get_file_knobs(node):
            path = knob.value()
            if path:
                is_var_path, var_path = sgtk.util.get_variable_path(
                    engine.sgtk, knob.value()
                )
                print(path, is_var_path, var_path)
                if is_var_path:
                    update_backup_knob(node, knob.name(), var_path)
                else:
                    # Remove the backup knob so if the user has changed the value and is no longer using
                    # the variable root path we don't keep overwriting it every time the script is loaded
                    remove_backup_knob(node, knob.name())


def node_create_callback():
    """
    Callback that updates the file knobs on the node being created with the current value of the env vars
    """
    for knob in get_file_knobs(nuke.thisNode()):
        backup_knob = nuke.thisNode().knob(to_backup_knob_name(knob.name()))
        if not backup_knob:
            continue
        try:
            knob.setValue(
                sgtk.util.ShotgunPath.expand(decode_backup_value(backup_knob.value()))
            )
        except ValueError:
            pass
