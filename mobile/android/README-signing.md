# Android release signing

Release builds are signed with a private upload key. Neither the keystore nor
its passwords are in this repo, and they must never be committed.

## How the build finds the key

`android/app/build.gradle.kts` looks for a `key.properties` file in two places,
in order:

1. `android/key.properties` — the standard Flutter location. Gitignored.
2. `~/.android/abct/key.properties` — where this project keeps the canonical
   copy, so no secret ever sits inside the working tree.

If neither exists, or the file is incomplete, or the keystore it names is
missing, the release build **falls back to debug signing and prints a warning**
rather than failing. A fresh clone and CI therefore still build; they just
produce an APK that cannot be distributed.

## key.properties format

```properties
storeFile=/absolute/path/to/abct-release.jks
storePassword=...
keyAlias=abct-release
keyPassword=...
```

## Generating a keystore

```sh
export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"

keytool -genkeypair -v \
  -keystore ~/.android/abct/abct-release.jks \
  -storetype PKCS12 \
  -keyalg RSA -keysize 4096 -validity 10000 \
  -alias abct-release \
  -dname "CN=ABCT, OU=ABCT Mobile, O=ABCT, L=Unspecified, ST=Unspecified, C=US"
```

Then `chmod 600` both the keystore and `key.properties`.

## Verifying what an APK was signed with

```sh
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
"$ANDROID_HOME"/build-tools/*/apksigner verify --print-certs \
  build/app/outputs/flutter-apk/app-release.apk
```

The debug key identifies itself as `CN=Android Debug, O=Android, C=US`. The
release key is `CN=ABCT, OU=ABCT Mobile, O=ABCT, ...`. If you see the former on
a build you meant to distribute, the key.properties lookup above failed.

## Back this up

Android identifies an app by its signing key. **If the keystore or its password
is lost, no already-installed copy of the app can ever be updated in place** —
every user has to uninstall and reinstall, losing local app data. Keep an
offline backup of `abct-release.jks` and its password somewhere separate from
this machine.
