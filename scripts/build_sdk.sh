#!/bin/sh
set -eu

qt_version=$1
source_sha256=$2
release=$3
repo=$(pwd)
work=$(mktemp -d /tmp/qt-freebsd-build.XXXXXX)
archive="qt-everywhere-src-${qt_version}.tar.xz"
source_url="https://download.qt.io/official_releases/qt/${qt_version%.*}/${qt_version}/single/${archive}"

export CMAKE_BUILD_PARALLEL_LEVEL=2
mkdir -p "$repo/dist" "$work/source" "$work/build"
fetch -o "$repo/dist/$archive" "$source_url"
test "$(sha256 -q "$repo/dist/$archive")" = "$source_sha256"
tar -xf "$repo/dist/$archive" -C "$work/source" --strip-components 1
cd "$work/build"
"$work/source/configure" -prefix /opt/qt-freebsd -release -shared -opensource -confirm-license \
  -submodules qtbase,qtdeclarative,qtshadertools -nomake examples -nomake tests \
  -opengl desktop -xcb -- -DCMAKE_PREFIX_PATH=/usr/local -DQT_INSTALL_CONFIG_INFO_FILES=ON
cmake --build . --parallel 2
cmake --install .

# Ship notices with the binaries and the matching complete source as a separate asset.
mkdir -p /opt/qt-freebsd/licenses
for module in qtbase qtdeclarative qtshadertools; do
  cp -R "$work/source/$module/LICENSES" "/opt/qt-freebsd/licenses/$module"
done
if test -d "$work/source/LICENSES"; then
  cp -R "$work/source/LICENSES" /opt/qt-freebsd/licenses/supermodule
fi

cd "$repo"
python3 scripts/sdk.py package --directory "$repo/dist" \
  --qt-version "$qt_version" --source-sha256 "$source_sha256" \
  --source-archive "$repo/dist/$archive" --runtime-packages runtime-packages.txt --release "$release"
