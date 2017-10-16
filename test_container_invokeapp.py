import os
import pytest
import re
import stat
import collections
import pexpect.replwrap


pytestmark = [
               pytest.mark.invokeapp,
             ]


#INVOKE_APP_PATH = "/usr/bin/invoke_app"
INVOKE_APP_PATH = "/opt/invokeapp/invoke_app -S"
PARAMETERS_PATH = "parameters.hz"
FILES = {
    'datafile1' : { 'contents' : 'this is datafile1',
                    'mode' : stat.S_IRUSR },
    'datafile2' : { 'contents' : 'this is datafile2',
                    'mode' : stat.S_IRUSR },
    'slow_echo' : { 'contents' : 'sleep 3; echo $*',
                    'mode' : stat.S_IRUSR },
}

TOOLXML = """<?xml version="1.0"?>
<run>
    <tool>
        <about>Press Simulate to view results.</about>
        <command>echo hi</command>
    </tool>
    <input>
        <string id = "name">
            <about>
                <label>Hello World Name</label>
                <description>Enter your name here</description>
            </about>
            <default>yourname</default>
        </string>
    </input>
</run>
"""

class TestContainerInvokeapp(object):


    def setup_method(self, method):

        self.shell = pexpect.replwrap.bash()

        # FIXME: need a variable to control removing files at
        #        the end of each test, and another to control
        #        removing files at the end of the suite.

        self.remove_files = []

        # FIXME: this needs to be done once per test suite
        # write data and script files to disk in the container.
        for fname,fprop in FILES.items():
            with open(fname,'w') as f:
                f.write(fprop['contents'])
            self.remove_files.append(os.path.join(os.getcwd(),fname))
            os.chmod(fname,fprop['mode'])


    def teardown_method(self, method):

        # FIXME: this needs to be done once per test suite
        # remove the executable and config files
        for fname in self.remove_files:
            os.remove(fname)

        self.shell = None


    def _run_invoke_app(self,command_str,parameters_text=None,with_tty=True):

        result = ''
        returncode = 0
        toolout = ''

        # setup the output object with named attributes
        # result is stdout and stderr combined
        # returncode is the exit status of the command
        # toolout is the portion of result believed to be from the application
        InvokeAppOutput = collections.namedtuple('InvokeAppOutput',
            ['result','returncode','toolout','command'])

        # we need to fake a session directory
        if parameters_text is not None:
            with open(PARAMETERS_PATH,'w') as f:
                f.write(parameters_text)
            self.remove_files.append(os.path.join(os.getcwd(),PARAMETERS_PATH))
            cmd = 'export TOOL_PARAMETERS={}'.format(PARAMETERS_PATH)
            self.shell.run_command(cmd)

        if with_tty is False:
            command_str = 'nohup ' + command_str + ' > nohup.out'
            self.remove_files.append(os.path.join(os.getcwd(),'nohup.out'))

        # run the command in xvfb to handle toolparams popup windows
        # command_str = 'xvfb-run --auto-servernum -s "-screen 0 800x600x24"' \
        #                 + command_str

        print command_str

        # run the invoke_app command
        result = self.shell.run_command(command_str)
        returncode = int(self.shell.run_command("echo $?").strip())


        if with_tty is False:
            # result will hold all of the output:
            # the nohup command's output as well as what was stored
            # in nohub.out
            # temporarily store nohup.out's output in toolout
            # while we check the returncode
            toolout = self.shell.run_command('cat nohup.out')
            result = result.strip() + toolout

        if returncode != 0:
            # seems to have been a problem running nohup or
            # invokeapp. return with what we got, don't try
            # to parse out application's output
            return InvokeAppOutput(result,returncode,toolout,command_str)

        # returnode was 0,
        # continue processing to find the application's output

        # grab what we think is the application's output
        matches = re.search("\nexec'ing[^\n]+\n(.*)",result,re.DOTALL)
        if matches is None:
            # not sure why we wouldn't see the pattern here
            # since invokeapp returned status 0
            pass

        # strip off submit metrics from toolout
        pattern = "=SUBMIT-METRICS=>.*$"
        toolout = re.sub(pattern,'',matches.group(1),flags=re.MULTILINE)
        toolout = toolout.strip()

        if with_tty is False:
            # cleanup output, removing "XIO:  fatal IO error 11"
            # messages that arise because we don't kill the X11
            # based background commands before killing the shell?
            toolout = re.sub(r'XIO.+remaining\.','',toolout,flags=re.DOTALL)
            toolout = toolout.strip()

        return InvokeAppOutput(result,returncode,toolout,command_str)


    def _find_bg_command(self,command_str):

        # 'ps aux | grep "command" | grep -v -e "bash\|grep"'
        cmd = 'ps aux | grep "{}" | grep -v -e "bash\|grep"'.format(command_str)
        print cmd

        # run the piped commands
        result = self.shell.run_command(cmd).strip()

        # parse the output looking for the command
        rexp = '(?P<user>[^\s]+)\s+' + \
               '(?P<pid>[^\s]+)\s+'  + \
               '(?P<cpu>[^\s]+)\s+'  + \
               '(?P<mem>[^\s]+)\s+'  + \
               '(?P<vsz>[^\s]+)\s+'  + \
               '(?P<rss>[^\s]+)\s+'  + \
               '(?P<tty>[^\s]+)\s+'  + \
               '(?P<stat>[^\s]+)\s+' + \
               '(?P<start>[^\s]+)\s+' + \
               '(?P<time>[^\s]+)\s+' + \
               '(?P<command>[^\n]+)'

        m = re.search(rexp,result)
        if m is None:
            return None

        # make sure we return the correct command
        if m.group('command') != command_str:
            # didn't find the correct command
            return None

        return m.groupdict()


    def test_1_command_no_templates(self):
        """launching invoke_app with one -C command (not template) should run the command
           ex: invoke_app -C "sh ./slow_echo hi"
           should produce: hi
        """

        # build our invoke_app command
        command = INVOKE_APP_PATH + ' -C "sh ./slow_echo hi"'

        expected_out = "hi"

        # run invoke_app
        r = self._run_invoke_app(command)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"\nSTDOUT\n%s' % (expected_out,r.toolout,r.result)


    def test_3_commands_no_templates(self):
        """launching invoke_app with multiple non-templated -C commands
           should run the last command.
           ex: invoke_app -C "sh ./slow_echo hi" -C "sh ./slow_echo bye" -C "sh ./slow_echo yeah"
           should produce: yeah
        """

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "sh ./slow_echo hi"' \
                  + ' -C "sh ./slow_echo bye"' \
                  + ' -C "sh ./slow_echo yeah"'

        expected_out = "yeah"

        # run invoke_app
        r = self._run_invoke_app(command)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': \nSTDOUT %s\n%s" % (command,"="*10,r.result)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_template_0_default_run_template_1(self):
        """launching invoke_app with one -C template command should
           launch toolparams to run the command
           ex: invoke_app -C "cat @@file(datafile1)"
           should launch: toolparams 'cat @@file(datafile1)'
           and produce: this is datafile1
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile1):%s" % os.path.join(os.getcwd(),'datafile1'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"'

        expected_out = FILES['datafile1']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_template_1_default_run_template_1(self):
        """launching invoke_app with one -C template command
           and one -C non-template command should launch
           toolparams to run the command. when the parameters file
           has a valid reference to file(datafile1), the templated
           command should be run.
           ex: invoke_app -C "cat @@file(datafile1)" -C "sh ./slow_echo hi"
           should launch: toolparams 'cat @@file(datafile1)' -default 'sh ./slow_echo hi'
           and produce: this is datafile1
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile1):%s" % os.path.join(os.getcwd(),'datafile1'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "sh ./slow_echo hi"'

        expected_out = FILES['datafile1']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_template_1_default_run_default(self):
        """launching invoke_app with one -C template command
           and one -C non-template command should launch
           toolparams to run the command. when the parameters file
           does not have a valid reference to file(datafile1), the
           non-templated command should be run.
           ex: invoke_app -C "cat @@file(datafile1)" -C "sh ./slow_echo hi"
           should launch: toolparams 'cat @@file(datafile1)' -default 'sh ./slow_echo hi'
           and produce: hi
        """

        # create our parameters file
        parameters_text = '\n'.join([])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "sh ./slow_echo hi"'

        expected_out = "hi"

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_default_1_template_run_template_1(self):
        """launching invoke_app with one -C non-template command
           and one -C template command should launch
           toolparams to run the command. when the parameters file
           has a valid reference to file(datafile1), the templated
           command should be run.
           ex: invoke_app -C "sh ./slow_echo hi" -C "cat @@file(datafile1)"
           should launch: toolparams 'cat @@file(datafile1)' -default 'sh ./slow_echo hi'
           and produce: this is datafile1
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile1):%s" % os.path.join(os.getcwd(),'datafile1'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "sh ./slow_echo hi"' \
                  + ' -C "cat @@file(datafile1)"'

        expected_out = FILES['datafile1']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_default_1_template_run_default(self):
        """launching invoke_app with one -C non-template command
           and one -C template command should launch
           toolparams to run the command. when the parameters file
           does not have a valid reference to file(datafile1), the
           non-templated command should be run.
           ex: invoke_app -C "sh ./slow_echo hi" -C "cat @@file(datafile1)"
           should launch: toolparams 'cat @@file(datafile1)' -default 'sh ./slow_echo hi'
           and produce: hi
        """

        # create our parameters file
        parameters_text = '\n'.join([])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "sh ./slow_echo hi"' \
                  + ' -C "cat @@file(datafile1)"'

        expected_out = "hi"

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_2_templates_0_default_run_template_1(self):
        """launching invoke_app with two -C template commands
           and zero -C non-template command should launch
           toolparams to run the command. when the parameters file
           has a valid reference to file(datafile1), the
           appropriate templated command should be run.
           ex: invoke_app -C "cat @@file(datafile1)" -C "cat @@file(datafile2)"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)'
           and produce: this is datafile1
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile1):%s" % os.path.join(os.getcwd(),'datafile1'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "cat @@file(datafile2)"'

        expected_out = FILES['datafile1']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_2_templates_0_default_run_template_2(self):
        """launching invoke_app with two -C template commands
           and zero -C non-template command should launch
           toolparams to run the command. when the parameters file
           has a valid reference to file(datafile2), the
           appropriate templated command should be run.
           ex: invoke_app -C "cat @@file(datafile1)" -C "cat @@file(datafile2)"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)'
           and produce: this is datafile2
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile2):%s" % os.path.join(os.getcwd(),'datafile2'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "cat @@file(datafile2)"'

        expected_out = FILES['datafile2']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_2_templates_1_default_run_template_1(self):
        """launching invoke_app with two -C template commands
           and one -C non-template command should launch
           toolparams to run the command. when the parameters file
           has a valid reference to file(datafile1), the
           appropriate templated command should be run.
           ex: invoke_app -C "cat @@file(datafile1)" -C "cat @@file(datafile2)" -C "sh ./slow_echo hi"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
           and produce: this is datafile1
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile1):%s" % os.path.join(os.getcwd(),'datafile1'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "cat @@file(datafile2)"' \
                  + ' -C "sh ./slow_echo hi"'

        expected_out = FILES['datafile1']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_2_templates_1_default_run_template_2(self):
        """launching invoke_app with two -C template commands
           and one -C non-template command should launch
           toolparams to run the command. when the parameters file
           has a valid reference to file(datafile2), the
           appropriate templated command should be run.
           ex: invoke_app -C "cat @@file(datafile1)" -C "cat @@file(datafile2)" -C "sh ./slow_echo hi"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
           and produce: this is datafile2
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile2):%s" % os.path.join(os.getcwd(),'datafile2'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "cat @@file(datafile2)"' \
                  + ' -C "sh ./slow_echo hi"'

        expected_out = FILES['datafile2']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_2_templates_1_default_run_default(self):
        """launching invoke_app with two -C template commands
           and one -C non-template command should launch
           toolparams to run the command. when the parameters file
           does not have a valid reference, the
           appropriate non-templated command should be run.
           ex: invoke_app -C "cat @@file(datafile1)" -C "cat @@file(datafile2)" -C "sh ./slow_echo hi"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
           and produce: hi
        """

        # create our parameters file
        parameters_text = '\n'.join([])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "cat @@file(datafile2)"' \
                  + ' -C "sh ./slow_echo hi"'

        expected_out = 'hi'

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_template_1_default_1_template_run_template_1(self):
        """launching invoke_app with one -C template command
           and one -C non-template command and a second
           -C template comamnd should launch toolparams
           to run the command. when the parameters file
           has a valid reference to file(datafile1), the
           appropriate templated command should be run.
           ex: invoke_app -C "cat @@file(datafile1)" -C "sh ./slow_echo hi" -C "cat @@file(datafile2)"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
           and produce: this is datafile1
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile1):%s" % os.path.join(os.getcwd(),'datafile1'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "sh ./slow_echo hi"' \
                  + ' -C "cat @@file(datafile2)"'

        expected_out = FILES['datafile1']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_template_1_default_1_template_run_template_2(self):
        """launching invoke_app with one -C template commands
           and one -C non-template command and a second
           -C template command should launch toolparams
           to run the command. when the parameters file
           has a valid reference to file(datafile2), the
           appropriate templated command should be run.
           ex: invoke_app -C "cat @@file(datafile1)" -C "sh ./slow_echo hi" -C "cat @@file(datafile2)"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
           and produce: this is datafile2
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile2):%s" % os.path.join(os.getcwd(),'datafile2'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "sh ./slow_echo hi"' \
                  + ' -C "cat @@file(datafile2)"'

        expected_out = FILES['datafile2']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_template_1_default_1_template_run_default(self):
        """launching invoke_app with one -C template command
           and one -C non-template command and a second
           -C template command should launch toolparams
           to run the command. when the parameters file
           does not have a valid reference, the
           appropriate non-templated command should be run.
           ex: invoke_app -C "cat @@file(datafile1)" -C "sh ./slow_echo hi" -C "cat @@file(datafile2)"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
           and produce: hi
        """

        # create our parameters file
        parameters_text = '\n'.join([])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "sh ./slow_echo hi"' \
                  + ' -C "cat @@file(datafile2)"'

        expected_out = 'hi'

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_default_2_templates_run_template_1(self):
        """launching invoke_app with one -C non-template command
           and two -C template commands should launch toolparams
           to run the command. when the parameters file
           has a valid reference to file(datafile1), the
           appropriate templated command should be run.
           ex: invoke_app -C "sh ./slow_echo hi" -C "cat @@file(datafile1)" -C "cat @@file(datafile2)"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
           and produce: this is datafile1
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile1):%s" % os.path.join(os.getcwd(),'datafile1'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "sh ./slow_echo hi"' \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "cat @@file(datafile2)"'

        expected_out = FILES['datafile1']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_default_2_templates_run_template_2(self):
        """launching invoke_app with one -C non-template command
           and two -C template commands should launch toolparams
           to run the command. when the parameters file
           has a valid reference to file(datafile2), the
           appropriate templated command should be run.
           ex: invoke_app -C "sh ./slow_echo hi" -C "cat @@file(datafile1)" -C "cat @@file(datafile2)"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
           and produce: this is datafile2
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile2):%s" % os.path.join(os.getcwd(),'datafile2'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "sh ./slow_echo hi"' \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "cat @@file(datafile2)"'

        expected_out = FILES['datafile2']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_1_default_2_template_run_default(self):
        """launching invoke_app with one -C non-template command
           and two -C template command should launch toolparams
           to run the command. when the parameters file
           does not have a valid reference, the
           appropriate non-templated command should be run.
           ex: invoke_app -C "sh ./slow_echo hi" -C "cat @@file(datafile1)" -C "cat @@file(datafile2)"
           should launch: toolparams 'cat @@file(datafile1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
           and produce: hi
        """

        # create our parameters file
        parameters_text = '\n'.join([])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "sh ./slow_echo hi"' \
                  + ' -C "cat @@file(datafile1)"' \
                  + ' -C "cat @@file(datafile2)"'

        expected_out = 'hi'

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_2_templates_1_default_run_index_1(self):
        """launching invoke_app with two -C template commands
           and one -C non-template command should launch
           toolparams to run the command. when the parameters file
           has a valid positional reference, the
           appropriate templated command should be run.
           ex: invoke_app -C "cat @@file(#1)" -C "cat @@file(datafile2)" -C "sh ./slow_echo hi"
           should launch: toolparams 'cat @@file(#1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
           and produce: this is datafile1
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile1):%s" % os.path.join(os.getcwd(),'datafile1'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(#1)"' \
                  + ' -C "cat @@file(datafile2)"' \
                  + ' -C "sh ./slow_echo hi"'

        expected_out = FILES['datafile1']['contents']

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


#    def test_positional_2_templates_1_default_run_index_1_1(self):
#        """launching invoke_app with two -C template commands
#           and one -C non-template command should launch
#           toolparams to run the command. when the parameters file
#           has two valid positional references, the first matching
#           templated command should be run.
#           ex: invoke_app -C "cat @@file(#1)" -C "cat @@file(#1) @@file(#2)" -C "sh ./slow_echo hi"
#           should launch: toolparams 'cat @@file(#1)' -or 'cat @@file(datafile2)' -default 'sh ./slow_echo hi'
#           and produce: this is datafile1
#        """
#
#        # create our parameters file
#        parameters_text = '\n'.join([
#            "file(datafile1):%s" % os.path.join(os.getcwd(),'datafile1'),
#            "file(datafile2):%s" % os.path.join(os.getcwd(),'datafile2'),
#        ])
#
#        # build our invoke_app command
#        command = INVOKE_APP_PATH \
#                  + ' -C "cat @@file(#1)"' \
#                  + ' -C "cat @@file(#1) @@file(#2)"' \
#                  + ' -C "sh ./slow_echo hi"'
#
#        expected_out = FILES['datafile1']['contents']
#
#        # run invoke_app
#        r = self._run_invoke_app(command,parameters_text)
#
#        # check stdout
#        assert r.returncode == 0, \
#            "Error while executing '%s': %s" % (command,r.toolout)
#
#        # parse the output
#        assert r.toolout == expected_out, \
#            'Error while executing "%s": ' % (command) \
#            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_positional_2_templates_1_default_run_index_1_2(self):
        """launching invoke_app with two -C template commands
           and one -C non-template command should launch
           toolparams to run the command. when the parameters file
           has two valid positional references, the first matching
           templated command should be run.
           ex: invoke_app -C "cat @@file(#1) @@file(#2)" -C "cat @@file(#1)" -C "sh ./slow_echo hi"
           should launch: toolparams 'cat @@file(#1) @@file(#2)' -or 'cat @@file(#1)' -default 'sh ./slow_echo hi'
           and produce:
           this is datafile1
           this is datafile2
        """

        # create our parameters file
        parameters_text = '\n'.join([
            "file(datafile1):%s" % os.path.join(os.getcwd(),'datafile1'),
            "file(datafile2):%s" % os.path.join(os.getcwd(),'datafile2'),
        ])

        # build our invoke_app command
        command = INVOKE_APP_PATH \
                  + ' -C "cat @@file(#1) @@file(#2)"' \
                  + ' -C "cat @@file(#1)"' \
                  + ' -C "sh ./slow_echo hi"'

        expected_out = "%s%s" % (FILES['datafile1']['contents'],
                                 FILES['datafile2']['contents'])

        # run invoke_app
        r = self._run_invoke_app(command,parameters_text)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_command_arguments_1(self):
        """launching invoke_app with the -A flag, sending additional arguments
           ex: invoke_app -C "sh ./slow_echo" -A "hi pete"
           should produce: hi pete
        """

        # build our invoke_app command
        command = INVOKE_APP_PATH + ' -C "sh ./slow_echo" -A "hi pete"'

        expected_out = "hi pete"

        # run invoke_app
        r = self._run_invoke_app(command)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_command_arguments_2(self):
        """launching invoke_app with a blank -A flag,
           sending an empty string as additional arguments
           ex: invoke_app -C "sh ./slow_echo hi" -A ""
           should produce: hi
        """

        # build our invoke_app command
        command = INVOKE_APP_PATH + ' -C "sh ./slow_echo hi" -A ""'

        expected_out = "hi"

        # run invoke_app
        r = self._run_invoke_app(command)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_background_command_1(self):
        """launching invoke_app with a single -c flag,
           launching a background command
           ex: invoke_app -C "sh ./slow_echo hi" -c "sleep 10"
           should produce: hi
        """

        # build our invoke_app command
        bg_cmd = "sleep 10"
        command = INVOKE_APP_PATH + ' -C "sh ./slow_echo hi" -c "' + bg_cmd + '"'

        expected_out = "hi"

        # run invoke_app
        r = self._run_invoke_app(command)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


        # check that the background job was started
        result = self._find_bg_command(bg_cmd)
        assert result is not None, \
            "Could not find background command: '%s'" % (bg_cmd)


    def test_working_directory_1(self):
        """launching invoke_app with a -d flag to change the working directory,
           # ex: invoke_app -C "sh \${SESSIONDIR}/slow_echo \${PWD}" -d ${HOME}
           # should produce: ${HOME}
           ex: invoke_app -C "sh \${HOME}/slow_echo \${PWD}" -d ${SESSIONDIR}
           should produce: ${SESSIONDIR}
        """

        # build our invoke_app command
#        homedir,err = self.ws.execute('sh ./slow_echo ${HOME}')
#        command = INVOKE_APP_PATH \
#            + ' -C "sh ./slow_echo \${PWD}" -d ${HOME}'

        slow_echo_path = os.path.join(os.getcwd(),'slow_echo')
        command = INVOKE_APP_PATH \
            + ' -C "sh ' + slow_echo_path + ' \${PWD}"' \
            + ' -d ${SESSIONDIR}'

        expected_out = self.shell.run_command('echo ${SESSIONDIR}').strip()

        # run invoke_app
        r = self._run_invoke_app(command)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_environment_variable_1(self):
        """launching invoke_app with a -e flag to set an environment variable,
           ex: invoke_app -C "sh ./slow_echo \${FOO}" -e FOO=blahh
           should produce: blahh
        """

        # build our invoke_app command
        expected_out = 'blahh'
        command = INVOKE_APP_PATH \
            + ' -C "sh ./slow_echo \${FOO}"' \
            + ' -e FOO={0}'.format(expected_out)


        # run invoke_app
        r = self._run_invoke_app(command)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_fullscreen_1(self):
        """launching invoke_app with a -f flag to
           not set the FULLSCREEN environment variable,
           ex: invoke_app -C "sh ./slow_echo \${FULLSCREEN}" -f
           should produce: ""
        """

        # build our invoke_app command
        slow_echo_path = os.path.join(os.getcwd(),'slow_echo')
        command = INVOKE_APP_PATH \
            + ' -C "sh ' + slow_echo_path + ' \${FULLSCREEN}"' \
            + ' -f'

        expected_out = ''

        # because invoke_app checks if the command is associated with a tty
        # before starting a window manager or setting the FULLSCREEN
        # environment variable, we have to nohup the command and capture
        # the output. set the "with_tty" parameter to False to run the
        # command with nohup and fake no tty

        # run invoke_app
        r = self._run_invoke_app(command, with_tty=False)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


    def test_fullscreen_2(self):
        """launching invoke_app without a -f flag to
           set the FULLSCREEN environment variable to "yes",
           ex: invoke_app -C "sh ./slow_echo \${FULLSCREEN}"
           should produce: yes
        """

        # build our invoke_app command
        slow_echo_path = os.path.join(os.getcwd(),'slow_echo')
        command = INVOKE_APP_PATH \
            + ' -C "sh ' + slow_echo_path + ' \${FULLSCREEN}"'

        expected_out = 'yes'

        # because invoke_app checks if the command is associated with a tty
        # before starting a window manager or setting the FULLSCREEN
        # environment variable, we have to nohup the command and capture
        # the output. set the "with_tty" parameter to False to run the
        # command with nohup and fake no tty

        # run invoke_app
        r = self._run_invoke_app(command, with_tty=False)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # strip off ratpoison banner text
        pattern = "ratpoison: There can be only ONE\..*$"
        toolout = re.sub(pattern,'',r.toolout,flags=re.MULTILINE).strip()

        # parse the output
        assert toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,toolout)


#    def test_nanowhim_1(self):
#        """launching invoke_app with a -n flag to
#           setup the nanowhim version,
#           ex: invoke_app -C "sh ./slow_echo " -n dev
#           should produce:
#        """
#
#        # build our invoke_app command
#        command = INVOKE_APP_PATH + ' -C "sh ./slow_echo ${FULLSCREEN}"'
#
#        expected_out = 'yes'
#
#        # run invoke_app
#        r = self._run_invoke_app(command)
#
#        # check stdout
#        assert r.returncode == 0, \
#            "Error while executing '%s': %s" % (command,r.toolout)
#
#        # parse the output
#        assert r.toolout == expected_out, \
#            'Error while executing "%s": ' % (command) \
#            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)
#


    def test_path_environment_variable_1(self):
        """launching invoke_app with a -p flag to set
           the PATH environment variable,
           ex: invoke_app -C "sh ./slow_echo \${PATH} | cut -d\":\" -f 1" -p /blahh
           should produce: /blahh
        """

        # build our invoke_app command
        expected_out = '/blahh'
        command = INVOKE_APP_PATH \
            + ' -C "sh ./slow_echo \${PATH} | cut -d\":\" -f 1"'\
            + ' -p {0}'.format(expected_out)


        # run invoke_app
        r = self._run_invoke_app(command)

        # check stdout
        assert r.returncode == 0, \
            "Error while executing '%s': %s" % (command,r.toolout)

        # parse the output
        assert r.toolout == expected_out, \
            'Error while executing "%s": ' % (command) \
            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)


#    def test_rappture_version_1(self):
#        """launching invoke_app with a -r flag to set the rappture version
#           ex: invoke_app -C "sh ./slow_echo hi" -r dev
#           should produce: hi
#        """
#
#        # write a tool.xml file in the workspace.
#        fname = 'tool.xml'
#        text = TOOLXML
#        with self.sftp.open(fname,mode='w') as f:
#            f.write(text)
#        self.remove_files.append(os.path.join(os.getcwd(),fname))
#
#        # build our invoke_app command
#        command = INVOKE_APP_PATH \
#            + ' -C "rappture -tool {0}" -r dev'.format(fname)
#
#        expected_out = 'hi'
#
#        # run invoke_app
#        r = self._run_invoke_app(command)
#
#        # check stdout
#        assert r.returncode == 0, \
#            "Error while executing '%s': %s" % (command,r.toolout)
#
#        # parse the output
#        assert r.toolout == expected_out, \
#            'Error while executing "%s": ' % (command) \
#            + 'expected "%s"\nreceived "%s"' % (expected_out,r.toolout)
#
#
#        matches = re.search("\nRAPPTURE_PATH = ([^\n]+)\n",r.stdout,re.DOTALL)



