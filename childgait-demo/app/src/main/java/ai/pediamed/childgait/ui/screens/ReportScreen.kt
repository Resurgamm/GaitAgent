package ai.pediamed.childgait.ui.screens

import ai.pediamed.childgait.data.model.BodyRegion
import ai.pediamed.childgait.data.model.CameraSlot
import ai.pediamed.childgait.data.model.Clip
import ai.pediamed.childgait.data.model.EvgsItem
import ai.pediamed.childgait.data.model.GaitView
import ai.pediamed.childgait.data.model.ItemScore
import ai.pediamed.childgait.data.model.Limb
import ai.pediamed.childgait.data.model.ScoreLabel
import ai.pediamed.childgait.data.model.SessionReport
import ai.pediamed.childgait.ui.theme.atypicalColor
import ai.pediamed.childgait.ui.theme.typicalColor
import ai.pediamed.childgait.util.formatDurationSeconds
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.IosShare
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReportScreen(
    report: SessionReport,
    onClipClick: (CameraSlot) -> Unit,
    onShare: () -> Unit,
    onNewSession: () -> Unit,
    modifier: Modifier = Modifier,
    isAnalyzing: Boolean = false,
    scoresReceived: Int = report.aggregated.size,
    scoresTotal: Int = 34,
) {
    var detailItem by remember { mutableStateOf<EvgsItem?>(null) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        if (isAnalyzing) {
            item {
                Text(
                    text = "Scoring $scoresReceived / $scoresTotal — results appear as each item finishes",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }

        item { SummaryCard(report, isAnalyzing = isAnalyzing, scoresReceived = scoresReceived, scoresTotal = scoresTotal) }

        item { SectionLabel("SOURCE CLIPS") }

        items(report.input.clips, key = { it.slot.name }) { clip ->
            ClipRow(
                clip = clip,
                quality = report.qualityOf(clip.slot),
                flagged = report.flaggedIn(clip.slot),
                onClick = { if (!isAnalyzing) onClipClick(clip.slot) },
            )
        }

        item {
            SectionLabel("EVGS ITEMS · ${report.flaggedCount} of ${report.totalItems} flagged")
        }

        EvgsItem.byRegion().forEach { (region, items) ->
            item(key = "region-${region.name}") { RegionHeader(region, items, report) }
            items(items, key = { it.code }) { evgsItem ->
                ItemRow(
                    item = evgsItem,
                    left = report.score(evgsItem, Limb.LEFT),
                    right = report.score(evgsItem, Limb.RIGHT),
                    onClick = { detailItem = evgsItem },
                )
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                OutlinedButton(
                    onClick = onShare,
                    enabled = !isAnalyzing,
                    modifier = Modifier.weight(1f),
                ) {
                    Icon(
                        Icons.Filled.IosShare,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text("Export JSON")
                }
                TextButton(
                    onClick = onNewSession,
                    enabled = !isAnalyzing,
                    modifier = Modifier.weight(1f),
                ) {
                    Text("New session")
                }
            }
        }
    }

    detailItem?.let { item ->
        ModalBottomSheet(onDismissRequest = { detailItem = null }, sheetState = sheetState) {
            ItemDetailSheet(item = item, report = report)
        }
    }
}

@Composable
private fun SummaryCard(
    report: SessionReport,
    isAnalyzing: Boolean = false,
    scoresReceived: Int = report.aggregated.size,
    scoresTotal: Int = 34,
) {
    val accent = if (report.overall == ScoreLabel.ATYPICAL) atypicalColor() else typicalColor()

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(
                text = if (isAnalyzing) "SCORING IN PROGRESS" else report.overall.label.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                color = accent,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = if (isAnalyzing) {
                    "$scoresReceived of $scoresTotal scores received"
                } else {
                    "${report.flaggedCount} of ${report.totalItems} items flagged"
                },
                style = MaterialTheme.typography.headlineSmall,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.height(10.dp))
            Text(
                text = report.patternSummary,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(14.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f))
            Spacer(Modifier.height(14.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(28.dp)) {
                Stat(
                    "Left limb",
                    "${report.aggregated.count { it.limb == Limb.LEFT && it.isAtypical }}/17",
                )
                Stat(
                    "Right limb",
                    "${report.aggregated.count { it.limb == Limb.RIGHT && it.isAtypical }}/17",
                )
                Stat("Mean conf.", "${(report.meanConfidence * 100).roundToInt()}%")
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: String) {
    Column {
        Text(
            text = value,
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun ClipRow(clip: Clip, quality: Float, flagged: Int, onClick: () -> Unit) {
            val accent = when (clip.slot) {
                CameraSlot.SAGITTAL -> SagittalAccent
                CameraSlot.CORONAL -> CoronalAccent
            }
            val scoreNote = when (clip.slot) {
                CameraSlot.SAGITTAL ->
                    "${clip.resolvableItems.size} items × 2 limbs (mirrored)"
                CameraSlot.CORONAL ->
                    "${clip.resolvableItems.size} items × 2 limbs"
            }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(width = 4.dp, height = 38.dp)
                .background(accent, RoundedCornerShape(2.dp))
        )
        Spacer(Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = "${clip.slot.label} clip",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Text(
                text = "${formatDurationSeconds(clip.video.durationMs)} · " +
                    "$scoreNote · " +
                    "$flagged flagged · quality ${(quality * 100).roundToInt()}%",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Icon(
            imageVector = Icons.Filled.ChevronRight,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.outline,
            modifier = Modifier.size(18.dp),
        )
    }
}

@Composable
private fun RegionHeader(region: BodyRegion, items: List<EvgsItem>, report: SessionReport) {
    val flagged = items.sumOf { item ->
        Limb.entries.count { report.score(item, it)?.isAtypical == true }
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = region.label,
            style = MaterialTheme.typography.titleSmall,
            color = MaterialTheme.colorScheme.onSurface,
        )
        Text(
            text = "$flagged flagged",
            style = MaterialTheme.typography.labelSmall,
            color = if (flagged > 0) atypicalColor() else MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ItemRow(item: EvgsItem, left: ItemScore?, right: ItemScore?, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = item.displayName,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Text(
                text = "${item.code} · ${item.view.label}",
                style = MaterialTheme.typography.labelSmall,
                color = if (item.view == GaitView.SAGITTAL) SagittalAccent else CoronalAccent,
            )
        }

        LimbChip("L", left)
        Spacer(Modifier.width(6.dp))
        LimbChip("R", right)

        Icon(
            imageVector = Icons.Filled.ChevronRight,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.outline,
            modifier = Modifier
                .padding(start = 4.dp)
                .size(18.dp),
        )
    }
}

@Composable
private fun LimbChip(limbLabel: String, score: ItemScore?) {
    if (score == null) {
        Box(
            modifier = Modifier
                .background(
                    MaterialTheme.colorScheme.outline.copy(alpha = 0.12f),
                    RoundedCornerShape(6.dp),
                )
                .padding(horizontal = 8.dp, vertical = 5.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = limbLabel,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontFamily = FontFamily.Monospace,
                )
                Spacer(Modifier.width(5.dp))
                Text(
                    text = "—",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.outline,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace,
                )
            }
        }
        return
    }

    val atypical = score.isAtypical
    val color = if (atypical) atypicalColor() else typicalColor()

    Box(
        modifier = Modifier
            .background(color.copy(alpha = 0.16f), RoundedCornerShape(6.dp))
            .padding(horizontal = 8.dp, vertical = 5.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = limbLabel,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontFamily = FontFamily.Monospace,
            )
            Spacer(Modifier.width(5.dp))
            Text(
                text = if (atypical) "!" else "ok",
                style = MaterialTheme.typography.labelSmall,
                color = color,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace,
            )
        }
    }
}

@Composable
private fun ItemDetailSheet(item: EvgsItem, report: SessionReport) {
    val accent = if (item.view == GaitView.SAGITTAL) SagittalAccent else CoronalAccent

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 20.dp, end = 20.dp, bottom = 36.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = "ITEM ${item.itemNumber} · ${item.code}",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = item.displayName,
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.onSurface,
        )

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Limb.entries.forEach { limb ->
                val score = report.score(item, limb)
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = limb.label,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        text = score?.label?.label ?: "—",
                        style = MaterialTheme.typography.titleMedium,
                        color = if (score?.isAtypical == true) atypicalColor() else typicalColor(),
                    )
                    Text(
                        text = score?.let { "confidence ${(it.confidence * 100).roundToInt()}%" }
                            ?: "",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f))

        Text(
            text = "SCORED FROM",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Limb.entries.forEach { limb ->
            val clip = report.clipFor(item, limb)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(width = 3.dp, height = 16.dp)
                        .background(accent, RoundedCornerShape(2.dp))
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = "${limb.label}: ${clip.slot.label} · ${clip.video.displayName}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }
        Text(
            text = observabilityNote(item.view),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Text(
            text = "DEFINITION",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = item.explanation,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface,
        )

        Text(
            text = "SCORING CRITERIA",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        item.criteria.forEach { criterion ->
            Text(
                text = "· $criterion",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

private fun observabilityNote(view: GaitView) = when (view) {
    GaitView.SAGITTAL ->
        "Sagittal items are scored from the matching side-view clip (L or R)."
    GaitView.CORONAL ->
        "Only resolvable front-on — the side-on clips cannot show rotation or side-to-side shift."
}
