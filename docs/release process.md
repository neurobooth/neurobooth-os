
This document describes the Neurobooth release process.

The goals for this process are:
1. To ensure consistency in Neurobooth deployments such that every environment is associated with a known release version. 
2. To ensure the code tested in staging is identical to the code deployed to production.
3. To make it easier to determine what code modifications are in each environment, and whether issues identified in one environment are likely to affect another. 

This process uses GitHub's release support. In this model, a release is a bundle of code with a name and a git tag. By convention, the release name and tag are the same.
The release name also appears in the deployed code so anyone looking at the environment can tell what version is deployed. In source, `neurobooth_os/current_config.py` holds the version inside a `version = ...` assignment. The file is marked as a generated file; the deployment scripts (`configs/checkout_and_deploy.bat` / `configs/version.bat`) overwrite the assignment with the real release tag at deploy time. A plain master checkout reads the sentinel `'NO VERSION SET'`.

Because deploy stamps the version in, **the source value is never edited by hand**. There is no pre-release version-bump commit and no post-release increment — release numbering is driven entirely by git tags + GitHub releases.

Release numbering should generally follow [Semantic Versioning guidelines](https://semver.org/). Until/unless we plan to publish a release to a public index server, development release names can be used. A development release name consists of the normal three-part numbering system with ".devN" appended. 

A release that isn't ready for production deployment should be flagged in GitHub as "pre-release" when created. The "pre-release" identifier is removed when the release is "published".  

The process: 

Development is performed on feature branches as usual. When complete, feature branches are merged into master. Frequent merges of small branches simplifies coordination between developers and makes it easier to review code. The rest of the process is as follows:

1. Create a candidate release in GitHub against master HEAD, ensuring that it is marked as "pre-release". This tags the code in the release to the current state in the git history. Do **not** edit `current_config.py` first — deploy will stamp it.
2. Deploy the candidate release into staging and complete testing.
3. Publish the release in GitHub (remove the "pre-release" flag).
4. Deploy the published release into production environment(s). 
 
Checking out and deploying releases: 

The examples below show how to checkout released code install it using pip. Release v0.0.1 is used for demonstration. 

To checkout a release without installing specify the tag and branch (master):
	`git checkout tags/<tag>`

To install a release using pip: 
	`pip install git+https://github.com/neurobooth/neurobooth-os@v0.0.1`

If desired, the release can be installed in a particular location using the -target flag

