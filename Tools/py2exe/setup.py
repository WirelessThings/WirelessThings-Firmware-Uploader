from distutils.core import setup
import py2exe

setup(windows=[{'script': '../../UploaderWizard.py',
				"icon_resources": [(1, '../../wt.ico')]
				}],
      data_files=[('', ['../../wt.ico', '../../UploaderWizard_defaults.cfg'])]
	  )