"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

Scene Breakdown UI and logic which shows the contents of the scene
 
"""
import nukescripts
import tempfile
import nuke
import os
import platform
import sys
import shutil

class BreakdownPanel(nukescripts.PythonPanel):
    """
    Breakdown UI
    """
    def __init__(self, app, templates):
        super(BreakdownPanel, self).__init__("Scene Breakdown")

        self._app = app
        self._templates = templates
        
        # static header widgets
        
        msg = ("Below is a breakdown of all the read nodes<br>"
               "in the current scene. Items in green color are <br>"
               "up to date, meaning that the latest version is being<br>"
               "used. Items in red are using an older version. Clicking<br>"
               "the update button will update these to use the latest version.")
        
        self.addKnob(nuke.Text_Knob("info", "", "<b>%s</b>" % msg))
        self.addKnob(nuke.Text_Knob("div", ""))

        self._widgets = []
        
        # and refresh
        self.refresh()

    def __add_widget(self, w):
        """
        Helper method.
        adds widget to dialog and to internal list
        """
        self.addKnob(w)
        self._widgets.append(w)

    def _create_widget(self, template, node, file_name):
        """
        Creates a widget for a single item 
        """
        
        
        # figure out if this is the latest one
        fields = template.get_fields(file_name)
        versions = self._app.engine.tank.find_files(template, fields, ["version"])
        version_numbers = [ template.get_fields(x).get("version") for x in versions ]
        higest_version = max(version_numbers)
        curr_version = fields["version"]
        out_of_date = (curr_version < higest_version)
        
        # layout of a widget
        #
        #
        # Node: Read1                
        # File: blalba.v003.#.exr    
        # Version: v003, up to date  
        # [select] [show in fs] [update] 
        # --------------------------------------------
        
        ws = nuke.Text_Knob("whitespace", "  ", "  ")
        self.__add_widget(ws)
        
        node_knob = nuke.Text_Knob(node.name(), "<b>Node:</b>", "%s" % node.name())
        self.__add_widget(node_knob)

        file_knob = nuke.Text_Knob(node.name(), "<b>File:</b>", "%s" % os.path.basename(file_name))
        self.__add_widget(file_knob)
        
        if out_of_date:
            # out of date!
            version_info_knob = nuke.Text_Knob(node.name(), "<b>Version:</b>", "<span style='color: #D65C33'>v%03d, Latest version: v%03d</span>" % (curr_version, higest_version))
        else:
            version_info_knob = nuke.Text_Knob(node.name(), "<b>Version:</b>", "<span style='color: #A5D9A5'>v%03d, Up to date.</span>" % curr_version)
        self.__add_widget(version_info_knob)

        # python button knob only accepts a string so need to jump through hoops >.<

        callback_str = "import tank; tank.engine().apps['sg_breakdown'].bdh.curr_ui.select('%s')" % node.name()
        select_knob = nuke.PyScript_Knob("select", "Select Node", callback_str)
        self.__add_widget(select_knob)

        callback_str = "import tank; tank.engine().apps['sg_breakdown'].bdh.curr_ui.show_in_fs('%s')" % node.name()
        show_in_fs_knob = nuke.PyScript_Knob("select", "Show in File System", callback_str)
        self.__add_widget(show_in_fs_knob)
        
        callback_str = "import tank; tank.engine().apps['sg_breakdown'].bdh.curr_ui.update('%s')" % node.name()
        update_knob = nuke.PyScript_Knob("update", "Update", callback_str)
        if not out_of_date:
            update_knob.setEnabled(False)
        self.__add_widget(update_knob)

        # divider and empty text line
        divider = nuke.Text_Knob("div", "")
        self.__add_widget(divider)
        

    def refresh(self):
        """
        Refreshes the breakdown
        """

        # clear widgets
        for w in self._widgets:
            self.removeKnob(w)
        
        self._widgets = []
        
        # scan scene
        for node in nuke.allNodes("Read"):
            file_name = node.knob("file").evaluate().replace("/", os.path.sep)
            # validate against all our templates
            for t in self._templates:
                if t.validate(file_name):
                    # cool, we regognize this
                    self._create_widget(t, node, file_name)
       
        if len(self._widgets) == 0:
            
            # no tank nodes in the scene!
            num_read_nodes = len( nuke.allNodes("Read") )
            if num_read_nodes == 0:
                # no read nodes in scene at all
                msg = "Looks like your scene does not have any read nodes at all! "
                
            else:
                # read nodes but no tank data
            
                msg = ("Found %d read nodes in your scene but none of these <br> "
                       "nodes refer to paths that Tank recognizes. <br>If you use paths "
                       "that Tank recognizes, Tank will be able to tell <br>you when "
                       "your scene is out of date and needs updating!" % num_read_nodes)
            
            self.__add_widget(nuke.Text_Knob("no_input", "", "<i>%s</i>" % msg))
            
        # lastly add a close button            
        self.__add_widget(nuke.Text_Knob("whitespace", "", "    "))
        
        self.okButton = nuke.Script_Knob("Close")
        self.__add_widget(self.okButton)
        
    ##########################################################################################
    # callbacks from buttons
    
    def update(self, node_name):
        """
        Callback.
        Updates to latest
        """
        nuke.root().begin()
        try:
            node = nuke.toNode(node_name)
            file_name = node.knob("file").evaluate().replace("/", os.path.sep)
            
            # get template
            template = self._app.engine.tank.resolve(file_name)
            
            # get highest version
            fields = template.get_fields(file_name)
            versions = self._app.engine.tank.find_files(template, fields, ["version"])
            version_numbers = [ template.get_fields(x).get("version") for x in versions ]
            higest_version = max(version_numbers)
            
            # calc new path
            fields["version"] = higest_version
            new_path = template.apply_fields(fields)
            node.knob("file").setValue(new_path)
                        
        finally:
            nuke.root().end()
        
        # and refresh UI
        self.refresh()
        
        
    
    def show_in_fs(self, node_name):
        """
        Callback.
        Shows the node path in the file system
        """
        nuke.root().begin()
        try:
            node = nuke.toNode(node_name)
            file_name = node.knob("file").evaluate().replace("/", os.path.sep)
            folder_name = os.path.dirname(file_name)
            
            if not os.path.exists(folder_name):
                nuke.message("The path %s does not exist!" % file_name)
                
            else:
                system = platform.system()
                
                # run the app
                if system == "Linux":
                    cmd = 'xdg-open "%s"' % folder_name
                elif system == "Darwin":
                    cmd = "open '%s'" % folder_name
                elif system == "Windows":
                    cmd = 'cmd.exe /C start "Folder" "%s"' % folder_name
                else:
                    raise Exception("Platform '%s' is not supported." % system)
                
                self._app.engine.log_debug("Executing command '%s'" % cmd)
                exit_code = os.system(cmd)
                if exit_code != 0:
                    self.log_error("Failed to launch '%s'!" % cmd)
        finally:
            nuke.root().end()
        

    def select(self, node_name):
        """
        Callback.
        Selects the node and centers around it
        """
        nuke.root().begin()
        try:
            node = nuke.toNode(node_name)
            for n in nuke.selectedNodes():
                n.knob("selected").setValue(False)            
            node.knob("selected").setValue(True)
            node = nuke.selectedNode()
            xC = node.xpos() + node.screenWidth()/2
            yC = node.ypos() + node.screenHeight()/2
            nuke.zoom( nuke.zoom(), [ xC, yC ])    
        finally:
            nuke.root().end()
        

