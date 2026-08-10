package com.teamcata.abct

import io.flutter.embedding.android.FlutterFragmentActivity

/**
 * local_auth hosts its biometric prompt in a fragment, so the engine's activity
 * must be a FragmentActivity. With the plain FlutterActivity every biometric
 * call fails at runtime with `no_fragment_activity`.
 */
class MainActivity : FlutterFragmentActivity()
