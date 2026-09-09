# Dependency license review for 2026.9.0

Reviewed on 2026-09-09 against the retained A100 candidate environment
`matric-eval-calver-candidate-3e86005` (Linux, CPython 3.11). The exact installed
license inventory and supporting file hashes are recorded in
[`release/license-policy.json`](../../release/license-policy.json). These reviews
resolve specific metadata gaps and ambiguous text detection; other distributions
and changed evidence still require their own policy decision.

| Distribution | Reviewed result | Evidence |
| --- | --- | --- |
| stop-sequencer 1.2.3 | Apache-2.0 | The released README and PKG-INFO, reproduced in installed METADATA, contain the author's Apache declaration despite empty structured license fields. |
| wget 3.2 | MIT option selected | The released and installed `wget.py` header explicitly offers MIT in addition to public domain. |
| cffi 2.1.0 | MIT-0 | Installed `License-Expression: MIT-0` agrees with the upstream license. No distribution override is needed. |
| SciPy 1.17.1 Linux wheel | BSD-3-Clause AND BSD-3-Clause-Open-MPI AND (GPL-3.0-or-later WITH GCC-exception-3.1) AND LGPL-2.1-or-later AND Qhull | Complete installed license inventory, including runtime and source-component notices. |

## Release archive and installed-file identity

Both small source archives were downloaded from their version-specific PyPI
release metadata on A100. Their SHA-256 values matched PyPI and the committed
`uv.lock`; archive members were read without executing package code.

| Archive | SHA-256 |
| --- | --- |
| stop-sequencer-1.2.3.tar.gz | `2eb719ff4cb57a79cf0ddc87b4bf7da11fc9e7a170005eaed17311b015b71d02` |
| wget-3.2.zip | `35e630eca2aa50ce998b9b1a127bb26b30dfee573702782aa982f875e3f16061` |

The installed `stop_sequencer/stop_sequencer.py` and `wget.py` have exactly the
same bytes as the corresponding source-archive members. Their hashes and the
installed METADATA hashes are mandatory evidence in the policy review. An
archive digest in the lock alone cannot establish the installed declaration.

The stop-sequencer README's Apache declaration is preserved in its
[version-specific PyPI metadata](https://pypi.org/pypi/stop-sequencer/1.2.3/json)
and [upstream README](https://github.com/hyunwoongko/stop-sequencer/blob/master/README.md).
The version-specific archive is the binding source; the moving upstream README
is corroboration. The exact README member hash is
`e1d3b67a6a85c1904a7b9d6311e5bca530657566472869abb80c207e11d79738`.

For wget, the MIT alternative is in the `wget.py` member of the
[3.2 source archive](https://files.pythonhosted.org/packages/47/6a/62e288da7bcda82b935ff0c6cfe542970f04e29c756b0e147251b2fb251f/wget-3.2.zip).
The public-domain label in [PyPI metadata](https://pypi.org/pypi/wget/3.2/json)
does not need to be converted into a different license. This Python distribution
is distinct from GNU Wget.

## cffi

The installed cffi 2.1.0 license file has SHA-256
`5ba24ddc57067f9249add644c3afc41a5d6dc37e23433ef759d95df370b0af63`.
The [version-tagged upstream license](https://github.com/python-cffi/cffi/blob/v2.1.0/LICENSE)
identifies MIT No Attribution, matching
[SPDX MIT-0](https://spdx.org/licenses/MIT-0.html). The policy therefore accepts
that exact identifier without overriding the package's declaration.

## SciPy and bundled components

The installed wheel's primary `LICENSE.txt` has SHA-256
`4daf14e37432e7026165979ecb7a39930707a3e89bef4876cfaf9dad36ed364a`.
It contains SciPy's BSD terms and the Linux-wheel component notices described in
[the version-tagged upstream wheel license](https://github.com/scipy/scipy/blob/v1.17.1/tools/wheels/LICENSE_linux.txt).
The actual installed `scipy.libs` directory contains OpenBLAS, libgfortran, and
libquadmath shared libraries. The review also includes all four additional
installed license files for uarray, pocketfft, DOP, and Qhull.

| Component | License retained in the review |
| --- | --- |
| SciPy, OpenBLAS, uarray, pocketfft, DOP | BSD-3-Clause |
| LAPACK within OpenBLAS | BSD-3-Clause-Open-MPI |
| libgfortran | GPL-3.0-or-later WITH GCC-exception-3.1 |
| libquadmath | LGPL-2.1-or-later |
| Qhull | Qhull |

The [GCC runtime exception](https://spdx.org/licenses/GCC-exception-3.1.html)
is an inseparable part of the libgfortran expression. It grants additional
permissions for eligible compiled combinations; it does not erase the runtime's
license or authorize arbitrary GPL dependencies. The full GPL text also refers
to AGPL and other GPL versions. Such references do not independently license
SciPy under those terms. The reviewed conjunction preserves libquadmath's LGPL
terms and [Qhull's distinct notice requirements](https://spdx.org/licenses/Qhull.html),
as well as the [LAPACK/Open MPI variant](https://spdx.org/licenses/BSD-3-Clause-Open-MPI.html).

These dependencies are installed separately and remain unmodified. Their code
and shared libraries are not included in matric-eval's wheel, sdist, or npm
archive. This review does not authorize bundling them, removing their notices,
or changing their source-distribution obligations. The policy keeps standalone
prohibited licenses prohibited and requires the exact reviewed license-file
inventory before using this SciPy classification.
