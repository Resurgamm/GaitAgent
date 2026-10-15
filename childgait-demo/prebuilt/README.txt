Prebuilt debug APK — a convenience, not the deliverable.

  app-arm64-v8a-debug.apk    arm64 devices and Apple Silicon emulators

Install:
  adb install -r prebuilt/app-arm64-v8a-debug.apk

This lets you see the app without installing the Android toolchain. It is a DEBUG build signed
with a throwaway debug key, so it is for inspection and testing only — never distribution.

It also goes stale the moment the source changes. To rebuild from source (and get the x86_64 and
universal variants too):

  ./setup-toolchain.sh
  source env.sh
  ./gradlew assembleDebug

All EVGS scores in this build are synthetic. The in-app banner says so.
