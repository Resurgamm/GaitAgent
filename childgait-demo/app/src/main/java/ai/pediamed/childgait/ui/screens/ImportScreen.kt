package ai.pediamed.childgait.ui.screens

import ai.pediamed.childgait.data.model.CameraSlot
import ai.pediamed.childgait.data.model.EvgsItem
import ai.pediamed.childgait.data.model.GaitView
import ai.pediamed.childgait.data.model.VideoSource
import ai.pediamed.childgait.util.formatDurationSeconds
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

/**
 * Two labeled slots: sagittal (side) and coronal (front).
 */
@Composable
fun ImportScreen(
    sagittal: VideoSource?,
    coronal: VideoSource?,
    isReadyToAnalyze: Boolean,
    onClipPicked: (CameraSlot, Uri) -> Unit,
    onClipCleared: (CameraSlot) -> Unit,
    onAnalyze: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var pickingFor by remember { mutableStateOf(CameraSlot.SAGITTAL) }

    val picker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
    ) { uri -> uri?.let { onClipPicked(pickingFor, it) } }

    fun launchPicker(slot: CameraSlot) {
        pickingFor = slot
        picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.VideoOnly))
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
    ) {
        Text(
            text = "New assessment",
            style = MaterialTheme.typography.headlineSmall,
            color = MaterialTheme.colorScheme.onBackground,
        )
        Text(
            text = "Add two clips: one side (sagittal) view and the walkway-end (coronal) camera. " +
                "Three to five seconds each is enough. Sagittal L/R scores come from the same clip.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 6.dp),
        )

        Spacer(Modifier.height(24.dp))

        ClipSlot(
            slot = CameraSlot.SAGITTAL,
            caption = "Lateral camera, side-on",
            resolves = "${EvgsItem.forView(GaitView.SAGITTAL).size} sagittal items · both limbs (mirrored)",
            video = sagittal,
            accent = SagittalAccent,
            onPick = { launchPicker(CameraSlot.SAGITTAL) },
            onClear = { onClipCleared(CameraSlot.SAGITTAL) },
        )

        Spacer(Modifier.height(14.dp))

        ClipSlot(
            slot = CameraSlot.CORONAL,
            caption = "Walkway-end camera, facing the child",
            resolves = "${EvgsItem.forView(GaitView.CORONAL).size} coronal items · both limbs",
            video = coronal,
            accent = CoronalAccent,
            onPick = { launchPicker(CameraSlot.CORONAL) },
            onClear = { onClipCleared(CameraSlot.CORONAL) },
        )

        Spacer(Modifier.height(24.dp))

        Button(
            onClick = onAnalyze,
            enabled = isReadyToAnalyze,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (isReadyToAnalyze) "Analyse session" else "Add both clips to continue")
        }

        Spacer(Modifier.height(28.dp))

        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant,
            ),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "WHY TWO CLIPS",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "Sagittal items are scored once from the side-view clip and applied to " +
                        "both limbs. Coronal items (hind-foot, pelvis, trunk shift) need the " +
                        "frontal camera. Together they cover all 17 items × 2 limbs — 34 scores.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }

        Spacer(Modifier.height(20.dp))

        Text(
            text = "Clips are uploaded to the assessment server for scoring.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun ClipSlot(
    slot: CameraSlot,
    caption: String,
    resolves: String,
    video: VideoSource?,
    accent: Color,
    onPick: () -> Unit,
    onClear: () -> Unit,
) {
    val filled = video != null

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onPick),
        colors = CardDefaults.cardColors(
            containerColor = if (filled) {
                MaterialTheme.colorScheme.surfaceVariant
            } else {
                MaterialTheme.colorScheme.surface
            },
        ),
        border = BorderStroke(
            width = if (filled) 0.dp else 1.dp,
            color = MaterialTheme.colorScheme.outline.copy(alpha = 0.5f),
        ),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .size(width = 4.dp, height = 52.dp)
                    .background(accent, RoundedCornerShape(2.dp))
            )
            Spacer(Modifier.width(14.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "${slot.label.uppercase()} · ${slot.shortHint}",
                    style = MaterialTheme.typography.labelSmall,
                    color = accent,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    text = video?.displayName ?: caption,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    text = video?.let { "${formatDurationSeconds(it.durationMs)} clip · $resolves" }
                        ?: resolves,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(Modifier.width(10.dp))

            if (filled) {
                Icon(
                    imageVector = Icons.Filled.CheckCircle,
                    contentDescription = "Selected",
                    tint = accent,
                    modifier = Modifier.size(22.dp),
                )
                IconButton(onClick = onClear) {
                    Icon(
                        imageVector = Icons.Filled.Close,
                        contentDescription = "Remove ${slot.label} clip",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(18.dp),
                    )
                }
            } else {
                Icon(
                    imageVector = Icons.Filled.Add,
                    contentDescription = "Add ${slot.label} clip",
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(24.dp),
                )
            }
        }
    }
}

internal val SagittalAccent = Color(0xFF5BC8FF)
internal val SagittalAccentR = Color(0xFF7AD4FF)
internal val CoronalAccent = Color(0xFFFFC14D)
