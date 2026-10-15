package ai.pediamed.childgait.pose

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.util.Log
import ai.pediamed.childgait.data.model.Clip
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.pose.PoseDetection
import com.google.mlkit.vision.pose.defaults.PoseDetectorOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import kotlin.coroutines.coroutineContext
import kotlin.math.max
import kotlin.math.min

/**
 * Runs ML Kit pose detection over the frames of one clip, on device.
 *
 * This part is genuinely real — only the EVGS scores are mocked. Detection runs over the whole
 * clip up front rather than live during playback, which keeps the video smooth and lets the
 * overlay simply look up the nearest sampled frame as the player advances.
 */
class PoseTracker(private val context: Context) {

    private val detector by lazy {
        PoseDetection.getClient(
            PoseDetectorOptions.Builder()
                .setDetectorMode(PoseDetectorOptions.SINGLE_IMAGE_MODE)
                .build()
        )
    }

    suspend fun track(clip: Clip): PoseTrack = withContext(Dispatchers.IO) {
        val uri = Uri.parse(clip.video.uri)
        val retriever = MediaMetadataRetriever()
        val frames = mutableListOf<PoseFrame>()

        try {
            retriever.setDataSource(context, uri)

            val stepMs = 1000L / SAMPLE_FPS
            val count = min(MAX_FRAMES, max(1, (clip.video.durationMs / stepMs).toInt()))

            for (index in 0 until count) {
                coroutineContext.ensureActive()

                val timestampMs = index * stepMs
                val bitmap = retriever.getFrameAtTime(
                    timestampMs * 1000L,
                    MediaMetadataRetriever.OPTION_CLOSEST_SYNC,
                )?.let(::downscale) ?: continue

                val landmarks = detect(bitmap)
                if (landmarks.isNotEmpty()) {
                    frames += PoseFrame(timestampMs = timestampMs, landmarks = landmarks)
                }
                bitmap.recycle()
            }
        } catch (e: Exception) {
            Log.w(TAG, "Pose tracking failed for the ${clip.view.label} clip", e)
        } finally {
            runCatching { retriever.release() }
        }

        PoseTrack(view = clip.view, frames = frames)
    }

    private fun detect(bitmap: Bitmap): List<Landmark> = try {
        val pose = Tasks.await(detector.process(InputImage.fromBitmap(bitmap, 0)))
        pose.allPoseLandmarks
            .filter { it.inFrameLikelihood >= MIN_LIKELIHOOD }
            .map { landmark ->
                Landmark(
                    type = landmark.landmarkType,
                    x = (landmark.position.x / bitmap.width).coerceIn(0f, 1f),
                    y = (landmark.position.y / bitmap.height).coerceIn(0f, 1f),
                    likelihood = landmark.inFrameLikelihood,
                )
            }
    } catch (e: Exception) {
        Log.w(TAG, "Pose detection failed on a frame", e)
        emptyList()
    }

    /** Full-resolution 2K frames are wasted work for ML Kit; cap the long edge. */
    private fun downscale(bitmap: Bitmap): Bitmap {
        val longEdge = max(bitmap.width, bitmap.height)
        if (longEdge <= MAX_EDGE_PX) return bitmap
        val scale = MAX_EDGE_PX.toFloat() / longEdge
        val scaled = Bitmap.createScaledBitmap(
            bitmap,
            (bitmap.width * scale).toInt().coerceAtLeast(1),
            (bitmap.height * scale).toInt().coerceAtLeast(1),
            true,
        )
        if (scaled != bitmap) bitmap.recycle()
        return scaled
    }

    fun close() {
        runCatching { detector.close() }
    }

    private companion object {
        const val TAG = "PoseTracker"
        const val SAMPLE_FPS = 12L
        const val MAX_FRAMES = 60
        const val MAX_EDGE_PX = 640
        const val MIN_LIKELIHOOD = 0.35f
    }
}
