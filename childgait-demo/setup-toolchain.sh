#!/usr/bin/env bash
#
# Installs a completely self-contained Android build toolchain into ./toolchain.
#
# Nothing is written outside this directory: not ~/.gradle, not ~/Library/Android,
# not the system Java. Deleting ./toolchain removes every trace.
#
# Idempotent — re-running skips anything already present.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TC="$ROOT/toolchain"
DL="$TC/.downloads"

JDK_URL="https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk_aarch64_mac_hotspot_17.0.20.1_1.tar.gz"
CMDLINE_URL="https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip"
GRADLE_VERSION="8.10.2"
GRADLE_URL="https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip"

mkdir -p "$DL"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- JDK 17
needs_jdk=0
if [ ! -x "$TC/jdk/bin/javac" ] || [ ! -x "$TC/jdk/bin/java" ]; then
  needs_jdk=1
elif ! "$TC/jdk/bin/java" -version >/dev/null 2>&1; then
  say "JDK present but broken — reinstalling"
  needs_jdk=1
fi

if [ "$needs_jdk" -eq 1 ]; then
  say "Installing Temurin JDK 17 (aarch64, ~186 MB)"
  rm -rf "$TC/jdk" "$DL/jdk.tar.gz"
  mkdir -p "$TC/jdk" "$DL"
  curl -fL --retry 5 --retry-delay 2 -o "$DL/jdk.tar.gz" "$JDK_URL"
  # Strip both the jdk-*/ wrapper and the macOS Contents/Home nesting.
  tar -xzf "$DL/jdk.tar.gz" -C "$TC/jdk" --strip-components=3
  if ! "$TC/jdk/bin/java" -version >/dev/null 2>&1; then
    echo "JDK install failed to produce a working java binary" >&2
    rm -rf "$TC/jdk" "$DL/jdk.tar.gz"
    exit 1
  fi
else
  say "JDK 17 already present"
fi
export JAVA_HOME="$TC/jdk"
export PATH="$JAVA_HOME/bin:$PATH"
java -version

# ---------------------------------------------------------------- Android SDK
SDK="$TC/android-sdk"
if [ ! -x "$SDK/cmdline-tools/latest/bin/sdkmanager" ]; then
  say "Installing Android command-line tools"
  [ -f "$DL/cmdline-tools.zip" ] || curl -fL --retry 3 -o "$DL/cmdline-tools.zip" "$CMDLINE_URL"
  rm -rf "$SDK/cmdline-tools"
  mkdir -p "$SDK/cmdline-tools"
  unzip -q "$DL/cmdline-tools.zip" -d "$SDK/cmdline-tools"
  # The zip unpacks to cmdline-tools/; sdkmanager requires it at cmdline-tools/latest/.
  mv "$SDK/cmdline-tools/cmdline-tools" "$SDK/cmdline-tools/latest"
else
  say "Android command-line tools already present"
fi
export ANDROID_HOME="$SDK"
export ANDROID_SDK_ROOT="$SDK"

say "Accepting SDK licenses and installing packages (~1.5 GB)"
yes | "$SDK/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$SDK" --licenses >/dev/null 2>&1 || true
"$SDK/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$SDK" \
  "platform-tools" \
  "platforms;android-35" \
  "build-tools;35.0.0"

# ---------------------------------------------------------------- Gradle
if [ ! -x "$TC/gradle/bin/gradle" ]; then
  say "Installing Gradle ${GRADLE_VERSION}"
  [ -f "$DL/gradle.zip" ] || curl -fL --retry 3 -o "$DL/gradle.zip" "$GRADLE_URL"
  rm -rf "$TC/gradle" "$TC/.gradle-unpack"
  mkdir -p "$TC/.gradle-unpack"
  unzip -q "$DL/gradle.zip" -d "$TC/.gradle-unpack"
  mv "$TC/.gradle-unpack/gradle-${GRADLE_VERSION}" "$TC/gradle"
  rmdir "$TC/.gradle-unpack"
else
  say "Gradle already present"
fi

mkdir -p "$TC/gradle-home"

# local.properties points AGP at our sandboxed SDK.
printf 'sdk.dir=%s\n' "$SDK" > "$ROOT/local.properties"

say "Toolchain ready"
cat <<EOF

  JDK          $TC/jdk
  Android SDK  $SDK
  Gradle       $TC/gradle
  Gradle home  $TC/gradle-home   (all dependency caches land here)

Next:
  source env.sh
  ./gradlew assembleDebug

EOF
