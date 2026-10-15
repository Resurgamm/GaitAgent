package ai.pediamed.childgait.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat

/**
 * A restrained clinical palette: desaturated teal for the app's own actions, amber for flagged
 * findings, and a deliberately unexciting surface so the video and the scores carry the screen.
 *
 * Amber rather than red for atypical findings — these are screening observations on children,
 * and red reads as alarm in a way that overstates what an EVGS item means.
 */
private val Teal = Color(0xFF3E8E8A)
private val TealDark = Color(0xFF7BC8C2)
private val Amber = Color(0xFFB26A00)
private val AmberDark = Color(0xFFFFB865)

val AtypicalLight = Color(0xFFB26A00)
val AtypicalDark = Color(0xFFFFB865)
val TypicalLight = Color(0xFF3E7A4E)
val TypicalDark = Color(0xFF86D19A)

private val DarkColors = darkColorScheme(
    primary = TealDark,
    onPrimary = Color(0xFF00201E),
    primaryContainer = Color(0xFF12504C),
    onPrimaryContainer = Color(0xFFB6ECE7),
    secondary = AmberDark,
    onSecondary = Color(0xFF3B2600),
    background = Color(0xFF101414),
    onBackground = Color(0xFFE0E4E3),
    surface = Color(0xFF161B1B),
    onSurface = Color(0xFFE0E4E3),
    surfaceVariant = Color(0xFF283231),
    onSurfaceVariant = Color(0xFFBEC9C7),
    outline = Color(0xFF6A7573),
    error = Color(0xFFFFB4AB),
)

private val LightColors = lightColorScheme(
    primary = Teal,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFB6ECE7),
    onPrimaryContainer = Color(0xFF00201E),
    secondary = Amber,
    onSecondary = Color.White,
    background = Color(0xFFFAFBFA),
    onBackground = Color(0xFF191C1C),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF191C1C),
    surfaceVariant = Color(0xFFDBE5E3),
    onSurfaceVariant = Color(0xFF3F4948),
    outline = Color(0xFF6F7977),
)

private val AppTypography = Typography(
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 22.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        letterSpacing = 0.5.sp,
    ),
)

@Composable
fun ChildGaitTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = if (darkTheme) DarkColors else LightColors
    val view = LocalView.current

    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !darkTheme
        }
    }

    MaterialTheme(
        colorScheme = colors,
        typography = AppTypography,
        content = content,
    )
}

/** Colour for a finding, resolved against the current theme. */
@Composable
fun atypicalColor(): Color = if (isSystemInDarkTheme()) AtypicalDark else AtypicalLight

@Composable
fun typicalColor(): Color = if (isSystemInDarkTheme()) TypicalDark else TypicalLight
