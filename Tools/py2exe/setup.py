from distutils.core import setup
import py2exe

setup(windows=[{'script': '../../FirmwareUploader/FirmwareUploader.py',
				"icon_resources": [(1, '../../FirmwareUploader/wt.ico')]
				}],
      data_files=[('', ['../../FirmwareUploader/wt.ico', '../../FirmwareUploader/FirmwareUploader_defaults.cfg'])]
	)
