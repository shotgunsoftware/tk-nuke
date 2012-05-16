"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

"""
import nuke
import tank
import time
import nukescripts
import tempfile
import os
import sys
import shutil

from tank import TankError

class PublishPanel(nukescripts.PythonPanel):
    """
    The modal UI which gathers information about the publish.
    """
    def __init__(self, app, write_node_handler):
        super(PublishPanel, self).__init__("Tank Publish")

        self.setMinimumSize(400, 400)
        self._app = app
        self._write_node_handler = write_node_handler
        self._cancelled = False

        #####################################################################################
        #
        # Prepare Tasks
        #
        
        # dict mapping menu text to task
        self._tasks = {}
        # add empty entry at the top         
        self._tasks["Do not associate this publish with a task"] = None
        # add the rest in order
        sg_tasks = self.__get_shotgun_tasks()

        for sg_task in sg_tasks:
            # proj | entity | taskname
            label = "%s | %s | %s" % (sg_task["project"]["name"], sg_task["entity"]["name"], sg_task["content"])
            self._tasks[label] = sg_task


        #####################################################################################
        #
        # Prepare Tank Types
        #
        self._all_tank_types = {}
        self._tank_types = {}

        for key, tank_types in self.__get_shotgun_tank_types().items():
            self._tank_types[key] = {}
            for tank_type in tank_types:
                self._all_tank_types[tank_type['code']] = tank_type
                self._tank_types[key][tank_type['code']] = tank_type
            # end for
        # end for

        #####################################################################################
        #
        # UI
        #
        
        self._current_wizard_page = 1

        # start tabs (wizard) area
        self.addKnob(nuke.BeginTabGroup_Knob())
        
        # add wizard pages
        self._p1_items = self.__create_first_page()
        self._p2_items = self.__create_second_page()

        # close wizard area
        self.addKnob(nuke.EndTabGroup_Knob())
        
        # finally some buttons
        self.addKnob(nuke.Text_Knob("div3", "", "   "))
        self.firstButton = nuke.Script_Knob("Button 1")
        self.addKnob(self.firstButton)
        self.secondButton = nuke.Script_Knob("Button 2")
        self.addKnob(self.secondButton)
        
        # set visibility etc
        self.__update_wizard_pages()

    def __get_render_nodes(self):
        """
        Get the tank write nodes for this scene.
        Returns a list where each entry is a dict with keyes node and has_renders.
        """
        nodes = []
        for tn in self._write_node_handler.get_nodes():
            nodes.append( {"node": tn, "has_renders": self._write_node_handler.exists_on_disk(tn) } )
        return nodes
        
    def __get_num_renders(self):
        """
        returns the number of renders that are available for publish.
        """
        num_renders = 0
        for v in self.__get_render_nodes():
            if v["has_renders"]:
                num_renders += 1
        return num_renders

    def __update_wizard_pages(self):
        
        """
        controls visibilty of wizard pages
        """

        if self._current_wizard_page == 1 and self.__get_num_renders() > 0:
            self.firstButton.setName("Cancel")
            self.secondButton.setName("Next >>>")
            
        elif self._current_wizard_page == 1 and self.__get_num_renders() == 0:        
            self.firstButton.setName("Cancel")
            self.secondButton.setName("Publish")
            
        else:
            self.firstButton.setName("<<< Back")
            self.secondButton.setName("Publish")
                  
        # make everything visible  
        for x in (self._p1_items + self._p2_items):
            x.clearFlag(nuke.INVISIBLE)
                    
        if self._current_wizard_page == 1:
            for x in self._p2_items:
                x.setFlag(nuke.INVISIBLE)
        else:
            for x in self._p1_items:
                x.setFlag(nuke.INVISIBLE)
            
    def addKnobAndRegister(self, knob, items):
        """
        Helper. Adds a knob to ui, adds it to items list and returns the object
        """
        self.addKnob(knob)
        items.append(knob)
        return knob

    def __create_first_page(self):
        """
        Creates the page which has tasks and description
        """
        
        items = []
        
        self._tab1 = self.addKnobAndRegister(nuke.Tab_Knob("page1", "Basic Info"), items)
        
        # get tasks
        dropdown_items = self._tasks.keys()
        
        # create task menu
        self.addKnobAndRegister(nuke.Text_Knob("div2", "", "   "), items)
        self.addKnobAndRegister(nuke.Text_Knob("div2", 
                                               "", 
                                               "Please choose a Task to associate this publish with"), items)
        self._taskKnob = self.addKnobAndRegister(nuke.Enumeration_Knob("task", "", dropdown_items), items)
         
        if len(dropdown_items) > 1:
            # first task found
            self._taskKnob.setValue(dropdown_items[1])
        else:
            # no task associated
            self._taskKnob.setValue(dropdown_items[0])
        
        # create type menu
        if self._tank_types.get('script'):
            self.addKnobAndRegister(nuke.Text_Knob("div2", "", "   "), items)
            self.addKnobAndRegister(nuke.Text_Knob("div2", 
                                                   "", 
                                                   "Please choose a Type of publish"), items)

            tank_types = sorted(self._tank_types['script'].keys())
            self._tankTypeKnob = self.addKnobAndRegister(
                nuke.Enumeration_Knob("type", "", tank_types),
                items
            )
        # end if


        self.addKnobAndRegister(nuke.Text_Knob("div2", "", "   "), items)
        self.addKnobAndRegister(nuke.Text_Knob("div2", "", "Enter a description of your changes"), items)
        self._commentKnob = self.addKnobAndRegister(nuke.Multiline_Eval_String_Knob("comment2", "", ""), items) 
        
        # leave some space
        self.addKnobAndRegister(nuke.Text_Knob("div2", "", "   "), items)
        self.addKnobAndRegister(nuke.Text_Knob("div2", "", "   "), items)
        
        return items
                
    def __create_second_page(self):
        """
        Creates the page which has a list of all render nodes
        """
        items = []
        
        self.addKnobAndRegister(nuke.Tab_Knob("page2", "Choose Renders"), items)
        self.addKnobAndRegister(nuke.Text_Knob("div2", "", "Select which renders you want to publish"), items) 
        
        self._render_nodes = []
        
        # go through all 
        for rn in self.__get_render_nodes():
            
            # get metadata
            node = rn["node"]
            has_renders = rn["has_renders"]    
            channel_name = self._write_node_handler.get_channel_from_node(node)
            chkbox_caption = "Channel %s (Node %s)" % (channel_name, node.name())
            # register UI
            self.addKnobAndRegister(nuke.Text_Knob("div", ""), items)
            chkbox = self.addKnobAndRegister(nuke.Boolean_Knob("chkbox", chkbox_caption, True), items)
            c_desc = self.addKnobAndRegister(nuke.Text_Knob("div2", 
                                                            "", 
                                                            "<small><i>Enter Render Details:</i></small>"), 
                                             items)
            comments = self.addKnobAndRegister( nuke.String_Knob("comment", "", ""), items)
            if self._tank_types.get('renders'):
                render_tank_type = self.addKnobAndRegister(nuke.Text_Knob("div2", 
                                                                "", 
                                                                "<small><i>Please choose a Type of publish:</i></small>"),
                                                            items)
                tank_types = sorted(self._tank_types['renders'].keys())
                tank_type_knob = self.addKnobAndRegister(
                    nuke.Enumeration_Knob("type", "", tank_types),
                    items
                )
            # end if

            if not has_renders:
                # disable it and ignore it for now
                chkbox.setEnabled(False)
                comments.setEnabled(False)
                c_desc.setEnabled(False)
                if self._tank_types.get('renders'):
                    tank_type_knob.setEnabled(False)
                # end if
            else:
                # add to our list of stuff
                data = {}
                data["node"] = node
                data["chkbox"] = chkbox
                data["comments"] = comments
                if self._tank_types.get('renders'):
                    data["tank_type"] = tank_type_knob
                # end if
                self._render_nodes.append(data)
                
        return items
        
        
    def __get_shotgun_tasks(self):
        """
        Attempts to extract the tasks for the current context.
        
        Assumes that the context contains an entity, but everything else is optional.
        """
        
        entity = self._app.engine.context.entity
        
        if entity is None:
            # no entity - bail!
            return []
        
        # get all tasks for entity
        fields = ["project", "entity", "content", "task_assignees", "step"]
        filters = [["entity", "is", entity]]
        sg_tasks = self._app.engine.shotgun.find("Task", filters, fields)
        
        # sort alphabetically by content
        sg_tasks.sort(key=lambda item: item["content"])

        if self._app.engine.context.task:
            # we have a task in the context
            # sort again so that the matching task is first, 
            # followed by matching steps, followed by the rest
            def _task_sort_key(sg_task):
                if sg_task["id"] == self._app.engine.context.task["id"]:
                    return 0
                else:
                    return 1
            sg_tasks.sort(key=_task_sort_key)
        
        elif self._app.engine.context.step:
            # no task but at least we have a step!
            # sort so that things with the right step comes out on top
            def _step_sort_key(sg_task):
                step = sg_task.get("step")
                if step is not None and step["id"] == self._app.engine.context.step["id"]:
                    return 0
                else:
                    return 1
            sg_tasks.sort(key=_step_sort_key)
            
        return sg_tasks

    def __get_shotgun_tank_types(self):
        """
        Get shotgun TankType Entities for values set for 'tank_type' in env file.
        """

        config_tank_types = self._app.get_setting('tank_types')

        if not config_tank_types:
            return {}
        # end if

        tank_types = {}
        for key, value in config_tank_types.items():
            filters = [['code', 'is', name] for name in value]
            order = [{"field_name":"code", "direction":"asc"}]
            fields = ['code']

            sg_tank_types = self._app.engine.shotgun.find(
                'TankType', 
                filters=filters, 
                fields=fields, 
                order=order, 
                filter_operator='any'
            )
            tank_types[key] = sg_tank_types
        # end for

        return tank_types
    # end def __get_shotgun_tank_types
        
    def knobChangedCallback(self, knob):
        """
        Called when a button is pressed
        """
        if knob == self.firstButton:
            # <<< Back and Cancel
            if self._current_wizard_page == 1:
                # cancel!
                self._cancelled = True
                self.finishModalDialog(False)
            else:
                # not first page - <<< back
                self._current_wizard_page = 1
            
            # set visibility, captions etc
            self.__update_wizard_pages()

        elif knob == self.secondButton:
            # >>> Next and Publish
            
            if self._current_wizard_page == 1:
                # validate
                if self.get_description() == "":
                    nuke.message("Please type in a description!")
                    return                        
            
            next_page = False
            if self._current_wizard_page == 1 and self.__get_num_renders() > 0:
                # are on the first page and there are renders.
                next_page = True
            
            if next_page:
                self._current_wizard_page = 2
            else:
                # either on page 2 or on page 1 with no renders. Finished.
                self.finishModalDialog(True)
            
            # set visibility, captions etc
            self.__update_wizard_pages()

    ###########################################################################################
    # 
    # methods for accessing the data entered by the user

    def cancelled(self):
        """
        returns true if dialog was cancelled
        """
        return self._cancelled 

    def get_description(self):
        """
        returns the description
        """
        return self._commentKnob.getText()
        
    def get_task(self):
        """
        returns the shotgun task id or none if no task is selected
        """
        return self._tasks[self._taskKnob.value()]

    def get_tank_type(self):
        """
        Return the TankType entity selected. Return None if on TankType is configured for app.
        """
        if not self._tank_types.get('script'):
            return None
        # end if
        return self._all_tank_types[self._tankTypeKnob.value()]
    # end def get_tank_type

    
    def get_render_settings(self):
        """
        returns a list of dictionaries each with the following keys:
        * node
        * enabled
        * comment
        """
        s = []
        for x in self._render_nodes:
            render = dict(
                node = x["node"],
                enabled = x["chkbox"].value(),
                comment = x["comments"].value(),
            )
            
            tank_type = x.get('tank_type')
            if tank_type: 
                tank_type = self._all_tank_types[tank_type.value()]
            # end if
            render['tank_type'] = tank_type

            s.append(render) 
        return s
        
