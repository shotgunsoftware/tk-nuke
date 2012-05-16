#!/usr/bin/env python
# ---------------------------------------------------------------------------------------------
# Copyright (c) 2009-2011, Shotgun Software Inc
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#  - Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
#  - Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
#  - Neither the name of the Shotgun Software Inc nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

__version__ = '0.2'

from optparse import OptionParser
import webbrowser
import urllib
import sys
import subprocess

class RevolverError(Exception):
    pass


def _launch_rv(base_url, cmd, source=None, path_to_rv=None):
    # Launch RV with the given list of args.
    args = ['-flags', 'ModeManagerPreload=shotgun_review_app']

    if not path_to_rv:
        # The command needs to be enclosed in quotes when using the rvlink protocol
        args.extend(['-eval', '\'%s\'' % cmd])
    else:
        # We also need to set the server if not going via the rvlink
        cmd = 'shotgun_review_app.theMode().setServer("%s"); %s' % (base_url, cmd)
        args.extend(['-eval', cmd])

    if source:
        args.append(source)
    
    # If no path to RV was provided, us the rvlink protocol to launch RV
    if not path_to_rv:
        # Encode the RV args. We'll use shotgun to redirect to the RV app via the rvlink 
        # custom protocol
        url = '%s/rvlink/baked/%s' % (base_url, (' ' + ' '.join(args)).encode('hex'))
        webbrowser.open(url)
        return

    subprocess.Popen([path_to_rv] + args)

def _serialize_mu_args(args):
    # Convert the list of key-value pairs to the equivalent Mu representation
 
    if not args:
        return ''

    joined_args = []
    for (key, value) in args:
        joined_args.append('("%s", "%s")' % (key, value))
        
    return '[(string, string)] {%s}' % ', '.join(joined_args) 

def launch_timeline(base_url, context, path_to_rv=None):
    """
    Launch the Revolver timeline to the given context, on the given base_url.
    
    :param base_url: The base url for Shotgun, i.e. https://mysg.shotgunstudio.com
    :type base_url: `str`
    :param context: Optional. A dictionary containing one of the following sets of key-value
        configurations:

        * A Shotgun entity
            * `type`: Must be one of the following entity types: 'Version', 'Asset', 
                      'Sequence', 'Shot', 'Playlist' or 'Page'. If using 'Page' the
                      page type *must* be a Version page.
            * `id`: The corresponding id for the entity

        * An asset type in a project
            * `asset_type`: The code for an asset type in Shotgun, e.g. 'Character',
                            'Environment', 'Prop', etc.
            * `project_id`: A Shotgun project id.

    :type context: `dict` 
    :param path_to_rv: Optional. Path to the RV executable. If omitted, RV will be started
       via a web browser using the rvlink protocol
    :type path_to_rv: `str`
    """
    
    if not base_url:
        raise RevolverError('A base url must be specified to launch the Revolver timeline')
    
    # Generate the url for the timeline
    base_url = base_url.rstrip('/')
    url = '%s/page/review_app' % base_url

    args = []
    if context:
        # Generate the list of URL parameters from the given context dictionary 
        if 'type' in context and 'id' in context:
            if context['type'] == 'Version':
                args.append(('version_id', context['id']))
            else:
                valid_entity_types = ['Version', 'Asset', 'Sequence', 'Shot', 'Playlist', 'Page']
                if context['type'] not in valid_entity_types:
                    raise RevolverError('Unsupported entity type %s for RV timeline. Must be '
                                        'one of %s' % (context['type'], ', '.join(valid_entity_types)))

                args.extend([('entity_type', context['type']), ('entity_id', context['id'])])
        elif 'asset_type' in context and 'project_id' in context:
            args.extend([('asset_type', context['asset_type']),
                         ('project_id', context['project_id'])])
        else:
            raise RevolverError('Invalid context supplied for the Revolver timeline. Context '
                                'must contain either entity "type" and "id" entries, or '
                                '"asset_type" and "project_id" entries.')

    # Convert the args to a Mu string representation
    ser_args = _serialize_mu_args(args)
    cmd = 'shotgun_review_app.theMode().launchTimeline(%s);' % ser_args

    # Open RV with this configuration
    return _launch_rv(base_url, cmd, None, path_to_rv) 

def launch_submit_tool(base_url, context, source_image_seq, qt_output_path=None, path_to_rv=None):
    """
    Launch the Revolver submit tool on the given base_url, using the given context to determine
    the task and entity link for the created Version, if possible. If the context is not
    a Task, then an entity and pipeline step id must be provided and a best guess will be made
    based on this information to determine the Task. An optional quicktime output path can be
    provided. If not provided, the quicktime will be generated to the same path as the source 
    images.
    
    :param base_url: The base url for Shotgun, i.e. https://mysg.shotgunstudio.com
    :type base_url: `str`
    :param context: Optional. A dictionary containing one of the following sets of key-value
        configurations:

        * A Shotgun task. If provided, no other context information is necessary:
            * `type`: Should be "Task"
            * `id`: The task id.

        * A Shotgun entity and pipeline step id. From this, Revolver will make a best guess as to the task that should be associated with the Version:
            * `type`: An entity type, e.g. "Shot", "Asset"
            * `id`: The associated id of the entity
            * `step_id`: The id of the pipeline step associated with this submission.
        
    :type context: `dict` 
    :param source_image_seq: The image sequence to be submitted
    :type source_image_seq: `str`
    :param qt_output_path: The path to which the quicktime for this submission should be generated.
    :type qt_output_path: `str`
    :param path_to_rv: Optional. Path to the RV executable. If omitted, RV will be started
       via a web browser using the rvlink protocol
    :type path_to_rv: `str`
    """

    if not base_url:
        raise RevolverError('A base url must be specified to launch the submit tool')
    
    if not source_image_seq:
        raise RevolverError('A source image sequence must be specified to launch the submit tool')
    
    # Generate the url for the submit tool
    base_url = base_url.rstrip('/')
    url = '%s/page/review_app_submit' % base_url
    
    # Generate the list of URL parameters from the given context dictionary
    args = []
    if context:
        if 'type' in context and 'id' in context:
            if context['type'] == 'Task':
                args.append(('task_id', context['id']))
            else:
                args.extend([('entity_type', context['type']), ('entity_id', context['id'])])

                if 'step_id' in context:
                    args.append(('step_id', context['step_id']))
        else:
            raise RevolverError('Invalid context supplied for submit tool. Context must contain '
                                '"type" and "id" entries.')
        
    # If an output path for the Quicktime was specified, we need to encode it so it can be passed
    # via the url
    if qt_output_path:
        args.append(('qt_output_path', urllib.quote_plus(qt_output_path)))
        
    # Convert the args to a Mu string representation
    ser_args = _serialize_mu_args(args)
    cmd = 'shotgun_review_app.theMode().launchSubmitTool(%s);' % ser_args

    # Open RV with this configuration
    return _launch_rv(base_url, cmd, source_image_seq, path_to_rv)     
    

def main():
    
    parser = OptionParser()
    
    parser.add_option('-u', '--base-url',
                      help='Required. The Shotgun base url to be used. Of the form: '
                           'https://mysg.shotgunstudio.com')
    
    parser.add_option('-m', '--mode', 
                      help='Optional. The mode in which to launch the review app. One of: "timeline", '
                           'or "submit". Defaults to "timeline".')
    
    parser.add_option('-v', '--version-id', 
                      help='Optional. A version id, in "timeline" mode.')
    
    parser.add_option('-y', '--entity-type',
                      help='Optional. An entity type, in "submit" mode if no Task id is provided, or in '
                           '"timeline" mode if no Version id has been provided ')
    
    parser.add_option('-e', '--entity-id',
                      help='Optional. An entity id, in "submit" mode if no Task id is provided, or in '
                           '"timeline" mode if no Version id has been provided.')

    parser.add_option('-a', '--asset-type',
                      help='Optional. The code for an asset type to show in "timeline" mode. Also requires '
                           'that --project-id be specified')

    parser.add_option('-p', '--project-id',
                      help='Optional. Required if using --asset-type.')
    
    parser.add_option('-t', '--task-id',
                      help='Optional. A task id, in "submit" mode.')
    
    parser.add_option('-s', '--step-id',
                      help='Optional. The id of a pipeline step, in "submit" mode if no Task id is provided.')
    
    parser.add_option('-i', '--source-image-sequence',
                      help='Required in "submit" mode. The source image sequence path.')
    
    parser.add_option('-o', '--quicktime-output-path',
                      help='Optional. An output path for the generated quicktime in "submit" mode. '
                           'If omitted, the quicktime will be generated in the same directory as '
                           'the source image sequence')

    parser.add_option('-r', '--path-to-rv',
                      help='Optional. The path to the RV executable. If omitted, RV will be started via a '
                           'web browser using the rvlink protocol.')
    
    (options, args) = parser.parse_args()
    
    if not options.mode:
        print 'INFO: No mode provided. Defaulting to "timeline" mode'
        options.mode = 'timeline'
    
    if options.mode not in ['timeline', 'submit']:
        print 'ERROR: Invalid review app mode: %s' % options.mode
        return 1

    if not options.base_url:
        print 'ERROR: A Shotgun base url must be specified'
        return 1

    context = None
    
    if options.mode == 'timeline':
        # Assemble a context dictionary from the command line options that were passed in
        if options.version_id:
            context = {'type': 'Version', 'id': options.version_id}
        elif options.entity_type and options.entity_id:
            context = {'type': options.entity_type, 'id': options.entity_id}
        elif options.asset_type and options.project_id:
            context = {'asset_type': options.asset_type, 'project_id': options.project_id}
            
        try:
            launch_timeline(options.base_url, context, options.path_to_rv)
        except Exception, e:
            print 'ERROR: %s' % e
            return 1

    elif options.mode == 'submit':
        # Assemble a context dictionary from the command line options that were passed in
        if options.task_id:
             context = {'type': 'Task', 'id': options.task_id}
        elif options.entity_type and options.entity_id:
            context = {'type': options.entity_type, 'id': options.entity_id}

            if options.step_id:
                context['step_id'] = options.step_id

        try:
            launch_submit_tool(options.base_url, context, options.source_image_sequence, 
                               options.quicktime_output_path. options.path_to_rv)
        except Exception, e:
            print 'ERROR: %s' % e
            return 1
        
    return 0

if __name__ == '__main__':
    sys.exit(main())
    
