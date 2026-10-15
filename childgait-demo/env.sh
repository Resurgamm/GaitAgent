# Source this file to enter the project-local build environment.
#
#   source env.sh
#   ./gradlew assembleDebug
#
# Everything resolves inside ./toolchain — the system Java, ~/.gradle and
# ~/Library/Android are never consulted or written to.

_CG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

export JAVA_HOME="$_CG_ROOT/toolchain/jdk"
export ANDROID_HOME="$_CG_ROOT/toolchain/android-sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export GRADLE_USER_HOME="$_CG_ROOT/toolchain/gradle-home"

export PATH="$JAVA_HOME/bin:$_CG_ROOT/toolchain/gradle/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"

echo "childgait-demo env active"
echo "  java   $(command -v java)"
echo "  gradle $(command -v gradle)"
echo "  sdk    $ANDROID_HOME"
