package ai.pediamed.childgait.pose

import ai.pediamed.childgait.data.model.GaitView
import com.google.mlkit.vision.pose.PoseLandmark

/**
 * One landmark, in normalised image coordinates so drawing does not depend on the resolution the
 * frame happened to be decoded at.
 */
data class Landmark(
    val type: Int,
    val x: Float,
    val y: Float,
    val likelihood: Float,
)

/** Landmarks detected in a single sampled frame. */
data class PoseFrame(
    val timestampMs: Long,
    val landmarks: List<Landmark>,
) {
    fun landmark(type: Int): Landmark? = landmarks.firstOrNull { it.type == type }
}

/** Every sampled frame of one clip, in ascending timestamp order. */
data class PoseTrack(
    val view: GaitView?,
    val frames: List<PoseFrame>,
) {
    val isEmpty: Boolean get() = frames.isEmpty()

    /** The sampled frame nearest a playback position. */
    fun frameAt(timestampMs: Long): PoseFrame? =
        frames.minByOrNull { kotlin.math.abs(it.timestampMs - timestampMs) }

    companion object {
        val EMPTY = PoseTrack(view = null, frames = emptyList())

        /**
         * Skeleton edges drawn between landmarks. Face landmarks are deliberately omitted: this
         * is pediatric clinical video, the faces are mosaicked, and gait assessment reads the
         * trunk and limbs.
         */
        val CONNECTIONS: List<Pair<Int, Int>> = listOf(
            PoseLandmark.LEFT_SHOULDER to PoseLandmark.RIGHT_SHOULDER,
            PoseLandmark.LEFT_SHOULDER to PoseLandmark.LEFT_ELBOW,
            PoseLandmark.LEFT_ELBOW to PoseLandmark.LEFT_WRIST,
            PoseLandmark.RIGHT_SHOULDER to PoseLandmark.RIGHT_ELBOW,
            PoseLandmark.RIGHT_ELBOW to PoseLandmark.RIGHT_WRIST,
            PoseLandmark.LEFT_SHOULDER to PoseLandmark.LEFT_HIP,
            PoseLandmark.RIGHT_SHOULDER to PoseLandmark.RIGHT_HIP,
            PoseLandmark.LEFT_HIP to PoseLandmark.RIGHT_HIP,
            PoseLandmark.LEFT_HIP to PoseLandmark.LEFT_KNEE,
            PoseLandmark.LEFT_KNEE to PoseLandmark.LEFT_ANKLE,
            PoseLandmark.LEFT_ANKLE to PoseLandmark.LEFT_HEEL,
            PoseLandmark.LEFT_HEEL to PoseLandmark.LEFT_FOOT_INDEX,
            PoseLandmark.LEFT_ANKLE to PoseLandmark.LEFT_FOOT_INDEX,
            PoseLandmark.RIGHT_HIP to PoseLandmark.RIGHT_KNEE,
            PoseLandmark.RIGHT_KNEE to PoseLandmark.RIGHT_ANKLE,
            PoseLandmark.RIGHT_ANKLE to PoseLandmark.RIGHT_HEEL,
            PoseLandmark.RIGHT_HEEL to PoseLandmark.RIGHT_FOOT_INDEX,
            PoseLandmark.RIGHT_ANKLE to PoseLandmark.RIGHT_FOOT_INDEX,
        )

        /** Landmarks worth drawing as joints, matching [CONNECTIONS]. */
        val JOINTS: List<Int> = listOf(
            PoseLandmark.LEFT_SHOULDER, PoseLandmark.RIGHT_SHOULDER,
            PoseLandmark.LEFT_ELBOW, PoseLandmark.RIGHT_ELBOW,
            PoseLandmark.LEFT_WRIST, PoseLandmark.RIGHT_WRIST,
            PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP,
            PoseLandmark.LEFT_KNEE, PoseLandmark.RIGHT_KNEE,
            PoseLandmark.LEFT_ANKLE, PoseLandmark.RIGHT_ANKLE,
            PoseLandmark.LEFT_HEEL, PoseLandmark.RIGHT_HEEL,
            PoseLandmark.LEFT_FOOT_INDEX, PoseLandmark.RIGHT_FOOT_INDEX,
        )

        /** Left-side landmarks, so the overlay can colour limbs by side. */
        val LEFT_SIDE: Set<Int> = setOf(
            PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_ELBOW, PoseLandmark.LEFT_WRIST,
            PoseLandmark.LEFT_HIP, PoseLandmark.LEFT_KNEE, PoseLandmark.LEFT_ANKLE,
            PoseLandmark.LEFT_HEEL, PoseLandmark.LEFT_FOOT_INDEX,
        )
    }
}
