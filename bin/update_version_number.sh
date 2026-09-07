#!/usr/bin/env bash
#
#   update_version_number.sh (C) 2026, Peter Sulyok
#   Update version number in all release-specific files.
#
set -e


function print_usage() {
  echo "usage: $(basename $0) <VERSION>"
  echo ""
  echo "  Update version number in all release-specific files."
  echo "  VERSION must be in X.Y.Z format (e.g. 5.1.1)"
  echo ""
  echo "  Files updated:"
  echo "    pyproject.toml       - Python package version"
  echo "    doc/smfc.1           - smfc man page version"
  echo "    doc/smfc-client.1    - smfc-client man page version"
  echo "    smfc.spec            - RPM Version field and new changelog entry"
  echo "    debian/changelog     - new DEB changelog entry"
  echo "    docker/DOCKER.md     - new entry in the # Versions chapter"
  exit 1
}


# Validate input.
if [ -z "$1" ]; then
  echo "Error: VERSION parameter is missing."
  print_usage
fi

VERSION="$1"

if ! echo "${VERSION}" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "Error: VERSION '${VERSION}' is not in X.Y.Z format."
  print_usage
fi

# Determine project root (script is in bin/).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 1. Update pyproject.toml
FILE="${PROJECT_ROOT}/pyproject.toml"
if [ ! -f "${FILE}" ]; then
  echo "Error: ${FILE} not found."
  exit 1
fi
sed -i "s/^version = \".*\"/version = \"${VERSION}\"/" "${FILE}"
echo "Updated ${FILE}"

# 2. Update doc/smfc.1
FILE="${PROJECT_ROOT}/doc/smfc.1"
if [ ! -f "${FILE}" ]; then
  echo "Error: ${FILE} not found."
  exit 1
fi
sed -i "s/^\.TH SMFC 1 smfc\\\\-.*/.TH SMFC 1 smfc\\\\-${VERSION}/" "${FILE}"
echo "Updated ${FILE}"

# 2b. Update doc/smfc-client.1
FILE="${PROJECT_ROOT}/doc/smfc-client.1"
if [ ! -f "${FILE}" ]; then
  echo "Error: ${FILE} not found."
  exit 1
fi
sed -i "s/^\.TH SMFC\\\\-CLIENT 1 smfc\\\\-.*/.TH SMFC\\\\-CLIENT 1 smfc\\\\-${VERSION}/" "${FILE}"
echo "Updated ${FILE}"

# 3. Update smfc.spec (Version field and prepend changelog entry)
FILE="${PROJECT_ROOT}/smfc.spec"
if [ ! -f "${FILE}" ]; then
  echo "Error: ${FILE} not found."
  exit 1
fi
sed -i "s/^Version:        .*/Version:        ${VERSION}/" "${FILE}"
if grep -q " - ${VERSION}-1" "${FILE}"; then
  echo "Updated ${FILE} (changelog entry for ${VERSION} already exists)"
else
  RPM_DATE=$(date "+%a %b %d %Y")
  NEW_ENTRY="* ${RPM_DATE} Peter Sulyok <peter@sulyok.net> - ${VERSION}-1\n- UPDATE WITH RELEASE NOTES"
  sed -i "s/^%changelog$/%changelog\n${NEW_ENTRY}\n/" "${FILE}"
  echo "Updated ${FILE}"
fi

# 4. Update debian/changelog (prepend new entry)
FILE="${PROJECT_ROOT}/debian/changelog"
if [ ! -f "${FILE}" ]; then
  echo "Error: ${FILE} not found."
  exit 1
fi
if grep -q "^smfc (${VERSION})" "${FILE}"; then
  echo "Updated ${FILE} (changelog entry for ${VERSION} already exists)"
else
  DEB_DATE=$(date -R)
  NEW_ENTRY="smfc (${VERSION}) unstable; urgency=medium\n\n  * UPDATE WITH RELEASE NOTES\n\n -- Peter Sulyok <peter@sulyok.net>  ${DEB_DATE}"
  sed -i "1i\\${NEW_ENTRY}\n" "${FILE}"
  echo "Updated ${FILE}"
fi

# 5. Update docker/DOCKER.md (insert a new entry in the # Versions chapter)
FILE="${PROJECT_ROOT}/docker/DOCKER.md"
if [ ! -f "${FILE}" ]; then
  echo "Error: ${FILE} not found."
  exit 1
fi
if grep -q "\*\*${VERSION}\*\*" "${FILE}"; then
  echo "Updated ${FILE} (Versions entry for ${VERSION} already exists)"
else
  DOC_DATE=$(date "+%Y.%m.%d")
  NEW_LINE="  - **${VERSION}** (${DOC_DATE}): UPDATE WITH RELEASE NOTES"
  sed -i "s#^See \[CHANGELOG.md\].*#&\n${NEW_LINE}#" "${FILE}"
  echo "Updated ${FILE}"
fi

# 6. Run uv sync to update uv.lock
if command -v uv &> /dev/null; then
  cd "${PROJECT_ROOT}"
  uv sync
  echo "Updated uv.lock"
else
  echo "Warning: uv not found, skipping uv.lock update. Run 'uv sync' manually."
fi

echo ""
echo "Version updated to ${VERSION} in all files."
echo "Please update the changelog entries marked with 'UPDATE WITH RELEASE NOTES' in:"
echo "  - smfc.spec"
echo "  - debian/changelog"
echo "  - docker/DOCKER.md"
