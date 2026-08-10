import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing material is deliberately kept out of the repo. key.properties
// is looked for in the standard Flutter spot first (android/key.properties,
// gitignored) and then in the developer's home, which is where this machine
// keeps the canonical copy so no secret ever sits in the working tree.
//
// Absent or incomplete, the release build falls back to debug signing with a
// warning instead of failing, so a fresh clone and CI can still build.
val releaseKeyProperties: Properties? = run {
    val file = listOf(
        rootProject.file("key.properties"),
        File(System.getProperty("user.home"), ".android/abct/key.properties"),
    ).firstOrNull { it.isFile } ?: return@run null

    val props = Properties().apply { file.inputStream().use { load(it) } }
    val missing = listOf("storeFile", "storePassword", "keyAlias", "keyPassword")
        .filter { props.getProperty(it).isNullOrBlank() }
    if (missing.isNotEmpty()) {
        logger.warn("ABCT: ${file.path} is missing ${missing.joinToString()} — using debug signing.")
        return@run null
    }
    if (!File(props.getProperty("storeFile")).isFile) {
        logger.warn("ABCT: keystore ${props.getProperty("storeFile")} not found — using debug signing.")
        return@run null
    }
    props
}

android {
    namespace = "com.teamcata.abct"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        // flutter_local_notifications needs java.time on API levels below 26.
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.teamcata.abct"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        releaseKeyProperties?.let { props ->
            create("release") {
                storeFile = File(props.getProperty("storeFile"))
                storePassword = props.getProperty("storePassword")
                keyAlias = props.getProperty("keyAlias")
                keyPassword = props.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = if (releaseKeyProperties != null) {
                signingConfigs.getByName("release")
            } else {
                logger.warn(
                    "ABCT: no release key.properties found — signing the release " +
                        "build with the DEBUG key. Fine for sideloading, but this " +
                        "APK cannot be distributed. See android/README-signing.md.",
                )
                signingConfigs.getByName("debug")
            }
        }
    }
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}

flutter {
    source = "../.."
}
