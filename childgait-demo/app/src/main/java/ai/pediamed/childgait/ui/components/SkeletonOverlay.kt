package ai.pediamed.childgait.ui.components

import ai.pediamed.childgait.pose.PoseFrame
import ai.pediamed.childgait.pose.PoseTrack
import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke

/**
 * Draws the detected skeleton over the video.
 *
 * The player is set to FIT, so the video sits letterboxed inside the view. We reproduce that
 * mapping here from [videoAspect] rather than stretching to the canvas, otherwise the skeleton
 * drifts off the subject on any clip whose aspect differs from the view's.
 *
 * Left and right limbs are coloured differently. EVGS is scored per limb, so being able to tell
 * the sides apart at a glance is the whole point of showing the skeleton at all.
 */
@Composable
fun SkeletonOverlay(
    track: PoseTrack,
    positionMs: Long,
    videoAspect: Float,
    modifier: Modifier = Modifier,
    leftColor: Color = Color(0xFF5BC8FF),
    rightColor: Color = Color(0xFFFFC14D),
    trunkColor: Color = Color(0xFFB8F2CE),
) {
    val frame = track.frameAt(positionMs) ?: return

    Canvas(modifier = modifier) {
        val content = contentRect(size, videoAspect)
        drawSkeleton(frame, content, leftColor, rightColor, trunkColor)
    }
}

/** The letterboxed rect the video actually occupies inside a FIT-scaled view. */
private fun contentRect(canvas: Size, videoAspect: Float): Rect {
    if (videoAspect <= 0f || canvas.width <= 0f || canvas.height <= 0f) {
        return Rect(Offset.Zero, canvas)
    }
    val canvasAspect = canvas.width / canvas.height
    return if (canvasAspect > videoAspect) {
        // Pillarboxed: full height, narrower than the canvas.
        val width = canvas.height * videoAspect
        val left = (canvas.width - width) / 2f
        Rect(Offset(left, 0f), Size(width, canvas.height))
    } else {
        // Letterboxed: full width, shorter than the canvas.
        val height = canvas.width / videoAspect
        val top = (canvas.height - height) / 2f
        Rect(Offset(0f, top), Size(canvas.width, height))
    }
}

private fun DrawScope.drawSkeleton(
    frame: PoseFrame,
    content: Rect,
    leftColor: Color,
    rightColor: Color,
    trunkColor: Color,
) {
    fun project(x: Float, y: Float) = Offset(
        x = content.left + x * content.width,
        y = content.top + y * content.height,
    )

    for ((startType, endType) in PoseTrack.CONNECTIONS) {
        val start = frame.landmark(startType) ?: continue
        val end = frame.landmark(endType) ?: continue

        val startIsLeft = startType in PoseTrack.LEFT_SIDE
        val endIsLeft = endType in PoseTrack.LEFT_SIDE
        val color = when {
            startIsLeft != endIsLeft -> trunkColor
            startIsLeft -> leftColor
            else -> rightColor
        }

        drawLine(
            color = color.copy(alpha = 0.9f),
            start = project(start.x, start.y),
            end = project(end.x, end.y),
            strokeWidth = BONE_WIDTH,
            cap = StrokeCap.Round,
        )
    }

    for (type in PoseTrack.JOINTS) {
        val landmark = frame.landmark(type) ?: continue
        val center = project(landmark.x, landmark.y)
        val color = if (type in PoseTrack.LEFT_SIDE) leftColor else rightColor
        drawCircle(color = Color.Black.copy(alpha = 0.55f), radius = JOINT_RADIUS + 1.5f, center = center)
        drawCircle(color = color, radius = JOINT_RADIUS, center = center)
        drawCircle(
            color = Color.White.copy(alpha = 0.8f),
            radius = JOINT_RADIUS,
            center = center,
            style = Stroke(width = 1.5f),
        )
    }
}

private const val BONE_WIDTH = 5f
private const val JOINT_RADIUS = 5.5f
