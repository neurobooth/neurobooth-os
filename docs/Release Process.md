
This document describes the Neurobooth release process.

The goals for this process are:
1. To ensure consistency in the Neurobooth deployment process such that every deployed environment is associated with a known release version. 
2. To ensure the code tested in staging is identical to the code deployed to production.
3. To make it easy to determine what code modifications are in each environment, and whether issues identified in one environment are likely to affect another. 

For simplicity, this process uses GitHub's release support. In this model, a release is a bundle of code with a name and a git tag. By convention, the release name and tag are the same, except that the 'V' indicating version is lowercase in the tag name and uppercase in the release name.  For example: Release V.0.0.1 should have tag v.0.0.1.

The release name also appears in the deployed code so anyone looking at the environment can tell what version is deployed. Keeping the version name in the code in sync with the release is a key part of the process. 

When release n is in development, `__version__` should say 'Vn-dev' (e.g. V0.0.2-dev)
When we're ready to make the release, the '-dev' part is stripped to provide the true version name (e.g. V0.0.2)
When the release has been created, `__version__` is incremented, and the '-dev' suffix is re-added.

(At some point this version name shuffling can be automated.)

A release that isn't ready for production deployment should be flagged as "pre-release" when created. The "pre-release" identifier is removed when the release is "published".  
The process: 

make a release (the new title should match the version in __init__.py, but more importantly, should be the next logical number from the last title used). Note that the release title starts with a capital V and the release tag starts with a lower-case v.

Development is performed on feature branches as usual. When complete, feature branches are merged into master.

1. To start the release process, update the version in neurobooth_os to match the planned release name. Usually, this just involves stripping the '-dev' string from the current value
3. The modified `__init__.py` is committed and pushed to master
4. Create a candidate release in GitHub, ensuring that it is marked as "pre-release" 
5. Deploy the candidate release into staging and complete testing in that environment 
6. Publish the release in GitHub 
7. Deploy the published release into production environments. 
8. Increment the version in `__init__.py` and append the string '-dev' 
9. Commit the new version
 
Deploying releases: 

The examples below show how to checkout released code install it using pip. Release V0.0.1 is used for demonstration. 

To install a release using pip: 
	pip install git+https://github.com/neurobooth/neurobooth-os@v0.0.1

To checkout a release:
	git checkout