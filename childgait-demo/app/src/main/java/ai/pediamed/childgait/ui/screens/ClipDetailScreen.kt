package ai.pediamed.childgait.ui.screens

import ai.pediamed.childgait.data.model.CameraSlot
import ai.pediamed.childgait.data.model.Clip
import ai.pediamed.childgait.data.model.ItemScore
import ai.pediamed.childgait.pose.PoseTrack
import ai.pediamed.childgait.ui.components.SkeletonOverlay
import ai.pediamed.childgait.ui.theme.atypicalColor
import ai.pediamed.childgait.ui.theme.typicalColor
import ai.pediamed.childgait.util.formatDurationSeconds
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.VideoSize
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.delay
import kotlin.math.roundToInt

/**
 * Loops one clip with the pose overlay, alongside the items that clip resolved.
 *
 * The clip is already short, so it plays whole and repeats — there is no window to trim to.
 */
@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
@Composable
fun ClipDetailScreen(
    clip: Clip,
    scores: List<ItemScore>,
    quality: Float,
    poseTrack: PoseTrack,
    isTrackingPose: Boolean,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var positionMs by remember { mutableLongStateOf(0L) }
    var videoAspect by remember { mutableFloatStateOf(DEFAULT_ASPECT) }

    val player = remember(clip.video.uri) {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(Uri.parse(clip.video.uri)))
            repeatMode = Player.REPEAT_MODE_ONE
            playWhenReady = true
            prepare()
        }
    }

    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onVideoSizeChanged(size: VideoSize) {
                if (size.width > 0 && size.height > 0) {
                    val pixelRatio =
                        if (size.pixelWidthHeightRatio > 0f) size.pixelWidthHeightRatio else 1f
                    videoAspect = size.width.toFloat() / size.height.toFloat() * pixelRatio
                }
            }
        }
        player.addListener(listener)
        onDispose {
            player.removeListener(listener)
            player.release()
        }
    }

    // Poll playback position to drive the overlay. Media3 has no per-frame callback, and 30 Hz
    // polling costs far less than decoding does.
    LaunchedEffect(player) {
        while (true) {
            positionMs = player.currentPosition
            delay(33)
        }
    }

    val accent = when (clip.slot) {
        CameraSlot.SAGITTAL -> SagittalAccent
        CameraSlot.CORONAL -> CoronalAccent
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(videoAspect.coerceIn(0.5f, 2.5f))
                .background(Color.Black),
        ) {
            AndroidView(
                factory = { ctx ->
                    PlayerView(ctx).apply {
                        useController = false
                        resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                        this.player = player
                    }
                },
                modifier = Modifier.fillMaxSize(),
            )

            SkeletonOverlay(
                track = poseTrack,
                positionMs = positionMs,
                videoAspect = videoAspect,
                modifier = Modifier.fillMaxSize(),
            )

            if (isTrackingPose) {
                Row(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(12.dp)
                        .background(Color.Black.copy(alpha = 0.55f), MaterialTheme.shapes.small)
                        .padding(horizontal = 10.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(12.dp),
                        strokeWidth = 1.5.dp,
                        color = Color.White,
                    )
                    Spacer(Modifier.size(8.dp))
                    Text(
                        text = "Detecting pose…",
                        style = MaterialTheme.typography.labelSmall,
                        color = Color.White,
                    )
                }
            }
        }

        val clipFraction = if (clip.video.durationMs > 0) {
            (positionMs.toFloat() / clip.video.durationMs).coerceIn(0f, 1f)
        } else {
            0f
        }
        LinearProgressIndicator(
            progress = { clipFraction },
            modifier = Modifier
                .fillMaxWidth()
                .height(3.dp),
        )

        Column(modifier = Modifier.padding(20.dp)) {
            Text(
                text = "${clip.slot.label} clip",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onBackground,
            )
            Text(
                text = clip.video.displayName,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = "${formatDurationSeconds(clip.video.durationMs)} · " +
                    "quality ${(quality * 100).roundToInt()}% · " +
                    if (poseTrack.isEmpty) "no pose data" else "${poseTrack.frames.size} pose frames",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(20.dp))

            Text(
                text = "RESOLVED FROM THIS CLIP · ${scores.size} SCORES",
                style = MaterialTheme.typography.labelSmall,
                color = accent,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = observabilityBlurb(clip.slot),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(12.dp))

            scores.forEach { score ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 7.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        text = score.item.displayName,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.weight(1f),
                    )
                    Text(
                        text = "${score.limb.code} ${if (score.isAtypical) "!" else "ok"}",
                        style = MaterialTheme.typography.labelSmall,
                        color = if (score.isAtypical) atypicalColor() else typicalColor(),
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
        }
    }
}

private fun observabilityBlurb(slot: CameraSlot) = when (slot) {
    CameraSlot.SAGITTAL ->
        "Side-on: sagittal ankle, knee, hip and trunk lean — scores applied to both limbs."
    CameraSlot.CORONAL ->
        "Front-on: hind-foot alignment, transverse rotation, pelvic obliquity and trunk shift."
}

private const val DEFAULT_ASPECT = 16f / 9f
