# Qt for FreeBSD

Build Qt once and share its installed SDK across FreeBSD CI jobs. The public
`Varinomics/qt-freebsd` releases contain Qt binaries, headers, tools, plugins,
configuration information, source identity and checksums. Consumer jobs download
an SDK; a missing release or incompatible SDK fails without compiling Qt.

The SDK profile is FreeBSD 15 amd64, native Clang/libc++, shared Release,
desktop OpenGL and XCB. It includes `qtbase`, `qtdeclarative` and
`qtshadertools`: Core, Gui and its private headers, Qml, Quick, Controls,
Layouts, Shapes, ShaderTools and Test. The offscreen platform plugin is included.
Consumers require Qt 6 with their own minimum version; an artifact's recorded
version identifies its contents and is not a ceiling on future compatible Qt.

## Consume an SDK

Run acquisition on the Ubuntu host before starting a FreeBSD VM:

```yaml
- uses: actions/checkout@v5
- name: Acquire Qt for FreeBSD
  id: qt-sdk
  uses: Varinomics/qt-freebsd@master
  with:
    minimum-qt-version: '6.12'
- uses: vmactions/freebsd-vm@v1
  env:
    QT_SDK_DIRECTORY: ${{ steps.qt-sdk.outputs.directory }}
    QT_SDK_PREFIX: ${{ steps.qt-sdk.outputs.prefix }}
  with:
    release: '15'
    cpu: 2
    envs: 'QT_SDK_DIRECTORY QT_SDK_PREFIX'
    prepare: |
      set -eu
      pkg bootstrap -fy
      mkdir -p /usr/local/etc/pkg/repos
      echo 'FreeBSD-ports: { enabled: no }' > /usr/local/etc/pkg/repos/FreeBSD-ports.conf
      echo 'FreeBSD: { url: https://pkg.FreeBSD.org/${ABI}/latest }' > /usr/local/etc/pkg/repos/FreeBSD.conf
      pkg update -f
      pkg install -y git cmake ninja pkgconf python3
    run: |
      set -eu
      python3 "$QT_SDK_DIRECTORY/sdk.py" install \
        --directory "$QT_SDK_DIRECTORY" --minimum-qt-version 6.12
      cmake -S . -B build -G Ninja -DCMAKE_PREFIX_PATH="$QT_SDK_PREFIX"
      cmake --build build --parallel 2
```

The action uses Python 3.11 or newer, selects GitHub's latest published stable
release once and fetches its exact assets. Public downloads work without a
cross-repository credential, including fork pull requests. The optional `token`
input defaults to `github.token` and authenticates only the release metadata API
request to avoid the anonymous API rate limit. Asset/CDN downloads carry no token.

The `directory` input defaults to `.qt-freebsd` and must remain beneath
`GITHUB_WORKSPACE` so the VM's normal source synchronization includes the files.
Outputs are `directory` (absolute workspace path), `prefix`
(`/opt/qt-freebsd`) and `release` (the selected release tag). The copied `sdk.py`
installer requires root privileges in the disposable FreeBSD VM. It verifies
checksums, Qt requirements, package ABI and the producer's minimum userland before
installing the runtime packages recorded in `sdk.json` and extracting the SDK.

The FreeBSD package repository must use the `latest` branch as in the example.
The consumer owns its build tools, Xvfb and project tests. The installer owns Qt's
runtime package list. Qt's installation prefix is fixed; arbitrary relocation is
not part of this contract. An existing installation at that prefix is rejected to
prevent headers, tools, plugins and libraries from different SDKs being mixed.

The SDK is built on the newest FreeBSD 15.x image selected by the VM action.
Its manifest records the actual userland version. Installation requires that
userland or a newer release within the FreeBSD 15 amd64 package ABI; binaries
built on a newer userland are not assumed to work on an older one. Compiler and
package versions are recorded as provenance. Required runtime libraries are
checked after installation, rather than rejecting an arbitrary newer compiler
version.

## Publish an SDK

Run the **Publish Qt for FreeBSD** workflow manually on `master`. Select the
official released Qt version and its matching source SHA-256. The workflow
accepts Qt 6.12 and newer Qt 6 releases and verifies the downloaded archive before
building it. Use the Qt download service's published checksum for that exact
archive. Changing Qt versions does not require changing consumer workflows when
the new SDK satisfies their minimum and component requirements.

Only the manual producer builds Qt. The workflow has no push, pull-request or
scheduled trigger. Its jobs:

1. Build with two CPUs, package the installed prefix and retain the original
   source archive as a separate release asset.
2. Download the produced archive into a fresh FreeBSD VM, install it through the
   same helper as consumers, resolve its CMake components and compile/run a small
   Quick application through XCB/OpenGL and offscreen presentation. No Qt source
   or build tree is present in this verification VM.
3. Create a new draft release, upload all assets and publish it as latest only
   after verification and upload succeed. Each run has a distinct release tag;
   the publisher never overwrites an earlier release's assets.

Only the publication job receives `contents: write`; its token is not forwarded
to the build or verification VMs. All producer runs share one concurrency group
so two publications cannot race to update the latest release.

Each release contains:

| Asset | Contents |
| --- | --- |
| `qt-freebsd-15-amd64.tar.xz` | Installed SDK and license notices, without source/build trees. |
| `sdk.json` | Qt/source identity, producer revision/run, FreeBSD baseline, native compiler, configuration, modules, installed package versions, runtime package names and SDK digest. |
| `SHA256SUMS` | SHA-256 of the SDK, manifest and source archive. |
| `qt-everywhere-src-<version>.tar.xz` | The matching complete official source archive. |

Qt's installed `config_*.opt` and `config_*.summary` files record the actual
configure results. `source-build-identity.json` inside the SDK must match the
release manifest's identity fields. Individual release assets are checked against
GitHub's 2 GiB limit before publication. Actions artifacts carry files between
producer jobs with one-day retention; consumers use durable release assets.

After first publication, validate the consuming projects against the downloaded
SDK using their existing FreeBSD tests. Publishing an SDK does not establish
those projects' integration results.

## Licensing

The producer/action code is under the BSD 2-Clause license in `LICENSE.txt`.
Qt and its bundled third-party components retain their upstream licenses. The
SDK includes module license notices; the separate matching source archive includes
the complete source and additional component notices. The SDK is not licensed
under this repository's BSD license.
