allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

// sentry_flutter 8.14.2 hardcodes kotlinOptions.languageVersion = "1.6", which the
// Kotlin 2.2 compiler shipped with Flutter 3.41 rejects outright. Raise any plugin
// asking for a language/API version below 1.8 up to 1.8.
subprojects {
    tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>().configureEach {
        val floor = org.jetbrains.kotlin.gradle.dsl.KotlinVersion.KOTLIN_1_8
        compilerOptions {
            languageVersion.set(
                languageVersion.orNull?.let { if (it < floor) floor else it } ?: floor,
            )
            apiVersion.set(
                apiVersion.orNull?.let { if (it < floor) floor else it } ?: floor,
            )
        }
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
