package ai.pediamed.childgait.di

import ai.pediamed.childgait.BuildConfig
import ai.pediamed.childgait.data.engine.GaitAnalyzer
import ai.pediamed.childgait.data.engine.RemoteGaitAnalyzer
import ai.pediamed.childgait.pose.PoseTracker
import android.content.Context

/**
 * Points the app at the EC2 assessment API.
 *
 * Multipart upload: sagittal + coronal → POST {API_BASE_URL}/v1/assessments/stream
 *
 * Keep [RemoteGaitAnalyzer.isMock] false when live inference (or streaming stub) is serving.
 */
object AppModule {

    /** No trailing slash. Set api.baseUrl in ignored local.properties. */
    const val API_BASE_URL = BuildConfig.API_BASE_URL

    @Volatile
    private var analyzer: GaitAnalyzer? = null

    fun gaitAnalyzer(context: Context): GaitAnalyzer =
        analyzer ?: synchronized(this) {
            analyzer ?: RemoteGaitAnalyzer(
                context = context.applicationContext,
                baseUrl = API_BASE_URL,
                isMock = false,
            ).also { analyzer = it }
        }

    fun poseTracker(context: Context): PoseTracker = PoseTracker(context.applicationContext)
}
