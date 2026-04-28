
# Question

Can I publish my python package to PyPI as part of a github CI workflow?

# Answer

Yes, you can absolutely publish your Python package to PyPI as part of a GitHub CI workflow. The current best practice is to use Trusted Publishing, which utilizes OpenID Connect (OIDC) to securely authenticate your GitHub repository with PyPI without needing to manage long-lived API tokens or secrets. [1, 2]
## 1. Set Up Trusted Publishing on PyPI [3]
Before your workflow can publish, you must authorize your repository on PyPI: [4]

* Log in to [PyPI](https://pypi.org/manage/account/publishing/) and go to Publishing > Add a new pending publisher.
* Select GitHub and provide your repository details:
* Owner/Organization Name and Repository Name.
   * Workflow Name: The filename of your YAML workflow (e.g., publish.yml).
   * Environment Name: (Optional but recommended) A GitHub environment name like pypi. [1, 4, 5, 6, 7]

## 2. Create the GitHub Actions Workflow [5]
Create a file at .github/workflows/publish.yml in your repository. A standard workflow typically triggers when you push a new tag or create a release. [1, 8, 9, 10, 11]

name: Publish to PyPIon:
  push:
    tags:
      - "v*.*.*" # Triggers when you push a version tag like v1.0.0
jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    # Required for OIDC Trusted Publishing
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.x"

      - name: Build distributions
        run: |
          python -m pip install build
          python -m build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1

[6, 12, 13]
## Key Security & Best Practices

* Permissions: Ensure the job explicitly includes permissions: id-token: write. This allows the pypa/gh-action-pypi-publish action to exchange a GitHub OIDC token for a temporary PyPI token.
* Environments: Using a [GitHub Environment](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment) (e.g., pypi) allows you to require manual approval before the package is actually published.
* TestPyPI: It is highly recommended to first test your workflow by publishing to [TestPyPI](https://test.pypi.org/) to ensure everything builds correctly before hitting the production index.
* Separate Build and Publish: For maximum security, you can separate the build and publish steps into different jobs, passing the built artifacts between them using actions/upload-artifact and actions/download-artifact. [1, 4, 5, 12, 14, 15, 16]

Do you already have a pyproject.toml file set up for your package, or would you like a template for that as well? [8]

[1] [https://packaging.python.org](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
[2] [https://www.buildwithmatija.com](https://www.buildwithmatija.com/blog/publish-to-pypi-guide)
[3] [https://www.pyopensci.org](https://www.pyopensci.org/python-package-guide/tutorials/trusted-publishing.html)
[4] [https://medium.com](https://medium.com/@nipunweerasiri/publishing-python-packages-to-pypi-using-uv-and-github-workflows-with-trusted-publishing-47bdfab162db)
[5] [https://www.pyopensci.org](https://www.pyopensci.org/blog/python-packaging-security-publish-pypi.html)
[6] [https://gist.github.com](https://gist.github.com/emrekgn/53b29e9ee8779f1a6c81fa0d25afdd8c)
[7] [https://github.com](https://github.com/lsst-sqre/build-and-publish-to-pypi)
[8] [https://medium.com](https://medium.com/@blackary/publishing-a-python-package-from-github-to-pypi-in-2024-a6fb8635d45d)
[9] [https://docs.github.com](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions)
[10] [https://dev.to](https://dev.to/ugglr/publish-update-npm-packages-with-github-actions-1m8l)
[11] [https://medium.com](https://medium.com/hostspaceng/triggering-workflows-in-another-repository-with-github-actions-4f581f8e0ceb#:~:text=In%20the%20target%20repository%20%28the%20one%20where,workflow%20you%20want%20to%20run%20when%20triggered.)
[12] [https://github.com](https://github.com/marketplace/actions/pypi-publish)
[13] [https://github.com](https://github.com/marketplace/actions/pypi-publish)
[14] [https://packaging.python.org](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
[15] [https://docs.github.com](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-pypi)
[16] [https://medium.com](https://medium.com/pythoneers/the-ultimate-guide-for-creating-and-uploading-python-packages-to-pypi-aea1ffada7fe)
