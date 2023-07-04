
This document describes the Neurobooth release process.

The goals for this process are:
1. To ensure consistency in Neurobooth deployments such that every environment is associated with a known release version. 
2. To ensure the code tested in staging is identical to the code deployed to production.
3. To make it easier to determine what code modifications are in each environment, and whether issues identified in one environment are likely to affect another. 

This process uses GitHub's release support. In this model, a release is a bundle of code with a name and a git tag. By convention, the release name and tag are the same.
The release name also appears in the deployed code so anyone looking at the environment can tell what version is deployed. In code, the name is stored in a `__version__` attribute in a way that is consistent with Python package naming standards. 
Specifically, the `__init__.py` module in the neurobooth-os folder holds the attribute.  

Keeping the version name in the code in sync with the release is a key part of the process:
- When release 0.0.4 is in development, `__version__ = "v0.0.4-dev"`
- When we're ready to release, the '-dev' part is removed and `__version__ = "v0.0.4"`. This version gets packaged into the release.
- When the release has been created, `__version__` is incremented, and the '-dev' suffix is restored so that `__version__ = "0.0.5-dev"`.

(At some point all this version name shuffling can be automated.)

A release that isn't ready for production deployment should be flagged as "pre-release" when created. The "pre-release" identifier is removed when the release is "published".  

The process: 

Development is performed on feature branches as usual. When complete, feature branches are merged into master. Frequent merges of small branches simplifies coordination between developers and makes it easier to review code. The rest of the process is as follows:

1. Update the `__version__` in neurobooth_os to match the planned release name, by removing the '-dev' suffix as described above.
3. The modified `__init__.py` is committed and pushed to master
4. Create a candidate release in GitHub, ensuring that it is marked as "pre-release". This tags the code in the release to the current state in the git history.
5. Increment the version in `__init__.py`, append the string '-dev', and commit the changes.
6. Deploy the candidate release into staging and complete testing 
6. Publish the release in GitHub 
7. Deploy the published release into production environment(s). 
 
Checking out and deploying releases: 

The examples below show how to checkout released code install it using pip. Release v0.0.1 is used for demonstration. 

To checkout a release without installing specify the tag and branch (master):
	`git checkout tags/<tag> -b <branch>`

To install a release using pip: 
	`pip install git+https://github.com/neurobooth/neurobooth-os@v0.0.1`

If desired, the release can be installed in a particular location using the -target flag
