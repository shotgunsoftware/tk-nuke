"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

"""
import nukescripts
import nuke
import os
import shutil
import datetime

from tank import TankError

class SnapshotAsPanel(nukescripts.PythonPanel):
    
    def __init__(self, app):
        super(SnapshotAsPanel, self).__init__("Tank Create New Snapshot" )

        self._app = app
        self._work_template = self._app.get_template("template_work")
        # compute suggested path and version number based on curr file.
        (self._suggested_name, self._curr_file_version) = self.__suggest_name_from_current_file("comp")
        
        # build UI
        
        self.addKnob(nuke.Text_Knob("info1", "", "Directory"))
        self._dir = nuke.Text_Knob("dir", "", "")
        self.addKnob(self._dir)
        
        
        
        self.addKnob(nuke.Text_Knob("div1", ""))
        
        name_info = nuke.Text_Knob("info2", "", "Name")
        self.addKnob(name_info)        
        
        self._name = nuke.String_Knob("name", "", self._suggested_name)
        self.addKnob(self._name)
        self._reset_version = nuke.Boolean_Knob("reset_version", "Reset Version No") 
        self.addKnob(self._reset_version)
        if self._curr_file_version == 0:
            # could not calculate version number based on file name
            # so don't allow it to be reset either
            self._reset_version.setEnabled(False)
        
        self.addKnob(nuke.Text_Knob("div1", ""))

        self.addKnob(nuke.Text_Knob("info3", "", "Filename Preview"))
        self._preview = nuke.Text_Knob("preview", "", "")
        self.addKnob(self._preview)

        # divider
        self.addKnob(nuke.Text_Knob("div2", ""))
                
        # finally some buttons
        self.okButton = nuke.Script_Knob("Snapshot")
        self.addKnob(self.okButton)
        self.cancelButton = nuke.Script_Knob("Cancel")
        self.addKnob(self.cancelButton)
        
        self._update_preview()

    def __calculate_path(self, name, version):
        """
        Calculates a path given name and version
        """
        fields = {}
        fields["name"] = name
        fields["version"] = version
        fields.update(self._app.engine.context.as_template_fields(self._work_template))
        return self._work_template.apply_fields(fields)
        
    def __get_version_number(self):
        """
        Returns the version number that should be used, based on UI settings
        """
        if self._curr_file_version == 0:
            # no current version found
            return 1
        if self._reset_version.value():
            # reset version number
            return 1 
        else:    
            return self._curr_file_version

    def __suggest_name_from_current_file(self, default_name_fallback):
        """
        try to extract the default name and version from the current file if possible
        if not, revert to default config 
        if no default value, use supplied param
        returns 0 for the version number if it could not be extracted.
        returns (name,version)
        """
        try:
            # first try to extract the current name from the current file
            curr_filename = nuke.root().name().replace("/", os.path.sep)
            fields = self._work_template.get_fields(curr_filename)
            name = fields["name"]
            version = fields["version"]
        except:
            # try to get default name and version
            version = 0
            nk = self._work_template.keys["name"]
            if nk.default is None:
                name = default_name_fallback
            else:
                name = nk.default
                
        # now make sure that the name is not already taken
        unique_name = name
        counter = 1
        while self._check_for_dupes(self.__calculate_path(unique_name, 1)) == True:
            # there are dupes
            unique_name = "%s%d" % (name, counter)
            counter += 1
                
        return (unique_name, version)
    
    def get_path(self):
        """
        Calculate the work file name
        """
        return self.__calculate_path(self._name.getText(), self.__get_version_number())
    
    def _check_for_dupes(self, path):
        """
        returns False if there are no dupes, True if there are
        """
        versions = self._app.engine.tank.find_files(self._work_template, 
                                                    self._work_template.get_fields(path), 
                                                    ["version"])
        if len(versions) > 0:
            return True
        else:
            return False
    
    def _update_preview(self):
        
        success = False
        message = ""
        try:
            self.okButton.setEnabled(False)
            
            # first check that the name field validates
            if not self._work_template.keys["name"].validate(self._name.getText()):
                message = "Invalid Characters in name!"
                success = False
            else:
                
                # name is valid. Check for dupes etc.
                preview_path = self.get_path()
                
                if self._check_for_dupes(preview_path):
                    message = "An file with this name already exists!"
                    success = False
                else:
                    # all good!            
                    self._preview.setValue(os.path.basename(preview_path))
                    self._dir.setValue(os.path.dirname(preview_path))
                    success = True
                    
        except Exception, e:
            self._app.engine.log_warning("The snapshot path could not be calculated: %s" % e)
            message = "An error was reported when evaluating the path."
            success = False
        
        if success:
            self.okButton.setEnabled(True)
        else:
            self.okButton.setEnabled(False)
            self._preview.setValue("<b style='color:orange;'>%s</b>" % message)
            
                
    def knobChanged(self, knob):
        self._update_preview()

        if knob == self.okButton:
            # make sure the file doesn't already exist
            self.finishModalDialog(True)
        elif knob == self.cancelButton:
            self.finishModalDialog(False)







class VersionUpPanel(nukescripts.PythonPanel):
    
    def __init__(self, curr_version):
        super(VersionUpPanel, self).__init__("Tank Set Version" )

        self._curr_version = curr_version
        
        # build UI        
        self.addKnob(nuke.Text_Knob("info1", 
                                    "", 
                                    ("Below you can change your current <br>version number "
                                    "without having to do a publish.")))
        self.addKnob(nuke.Text_Knob("div1", ""))
        
        self.addKnob( nuke.Text_Knob("info2", "Current Version", "%s" % self._curr_version))
        
        self._set_version = nuke.Int_Knob("new_version", "Set New Version")
        self._set_version.setValue(self._curr_version+1)
        self.addKnob(self._set_version)
        
        self.addKnob(nuke.Text_Knob("div1", ""))
                
        # finally some buttons
        self.okButton = nuke.Script_Knob("Set Version")
        self.addKnob(self.okButton)
        self.cancelButton = nuke.Script_Knob("Cancel")
        self.addKnob(self.cancelButton)
        
        self._update_preview()

    def get_new_version(self):
        """
        returns the new version number
        """
        return int(self._set_version.value())

    def _update_preview(self):
        # disable ok button if version number is wrong
        if self.get_new_version() > self._curr_version:
            self.okButton.setEnabled(True)
        else:
            self.okButton.setEnabled(False)
                
    def knobChanged(self, knob):
        self._update_preview()

        if knob == self.okButton:
            # make sure the file doesn't already exist
            self.finishModalDialog(True)
        elif knob == self.cancelButton:
            self.finishModalDialog(False)

