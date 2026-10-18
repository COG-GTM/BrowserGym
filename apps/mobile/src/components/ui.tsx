import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import type { ComponentProps, ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type TextStyle,
  type ViewStyle,
} from 'react-native';

import { useTheme } from '@/theme/ThemeProvider';

export type IconName = ComponentProps<typeof Ionicons>['name'];

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const t = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: t.colors.surface,
          borderColor: t.colors.border,
          borderWidth: StyleSheet.hairlineWidth,
          borderRadius: t.radius.lg,
          padding: t.spacing.lg,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function SText({
  children,
  variant = 'body',
  color,
  style,
  numberOfLines,
  testID,
}: {
  children: ReactNode;
  variant?: 'caption' | 'body' | 'bodyStrong' | 'title' | 'largeTitle' | 'mono';
  color?: 'text' | 'muted' | 'subtle' | 'accent' | 'danger' | 'success';
  style?: StyleProp<TextStyle>;
  numberOfLines?: number;
  testID?: string;
}) {
  const t = useTheme();
  const colorMap = {
    text: t.colors.text,
    muted: t.colors.textMuted,
    subtle: t.colors.textSubtle,
    accent: t.colors.accent,
    danger: t.colors.danger,
    success: t.colors.success,
  };
  return (
    <Text
      testID={testID}
      numberOfLines={numberOfLines}
      style={[t.font[variant], { color: colorMap[color ?? 'text'] }, style]}
    >
      {children}
    </Text>
  );
}

export function Button({
  title,
  onPress,
  variant = 'primary',
  icon,
  loading,
  disabled,
  style,
  testID,
  accessibilityLabel,
}: {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  icon?: IconName;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  accessibilityLabel?: string;
}) {
  const t = useTheme();
  const bg = {
    primary: t.colors.accent,
    secondary: t.colors.surfaceAlt,
    danger: t.colors.danger,
    ghost: 'transparent',
  }[variant];
  const fg = {
    primary: t.colors.accentText,
    secondary: t.colors.text,
    danger: '#fff',
    ghost: t.colors.accent,
  }[variant];
  const inactive = disabled || loading;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? title}
      accessibilityState={{ disabled: Boolean(inactive), busy: Boolean(loading) }}
      disabled={inactive}
      onPress={() => {
        Haptics.selectionAsync().catch(() => undefined);
        onPress();
      }}
      style={({ pressed }) => [
        {
          backgroundColor: bg,
          borderRadius: t.radius.md,
          paddingVertical: 12,
          paddingHorizontal: t.spacing.lg,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
          gap: t.spacing.sm,
          opacity: inactive ? 0.5 : pressed ? 0.8 : 1,
        },
        style,
      ]}
    >
      {loading ? <ActivityIndicator color={fg} size="small" /> : icon ? <Ionicons name={icon} size={18} color={fg} /> : null}
      <Text style={[t.font.bodyStrong, { color: fg }]}>{title}</Text>
    </Pressable>
  );
}

export function Chip({
  label,
  selected,
  onPress,
  color,
  testID,
}: {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  color?: string;
  testID?: string;
}) {
  const t = useTheme();
  const tint = color ?? t.colors.accent;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ selected: Boolean(selected) }}
      onPress={() => {
        Haptics.selectionAsync().catch(() => undefined);
        onPress?.();
      }}
      style={({ pressed }) => ({
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: t.radius.pill,
        borderWidth: 1,
        borderColor: selected ? tint : t.colors.border,
        backgroundColor: selected ? tint : t.colors.surface,
        opacity: pressed ? 0.75 : 1,
      })}
    >
      <Text style={{ fontSize: 13, fontWeight: '600', color: selected ? t.colors.accentText : t.colors.text }}>
        {label}
      </Text>
    </Pressable>
  );
}

export function TextField({
  label,
  hint,
  style,
  ...props
}: TextInputProps & { label?: string; hint?: string }) {
  const t = useTheme();
  return (
    <View style={{ gap: t.spacing.xs }}>
      {label ? <SText variant="caption" color="muted" style={{ fontWeight: '600' }}>{label.toUpperCase()}</SText> : null}
      <TextInput
        placeholderTextColor={t.colors.textSubtle}
        accessibilityLabel={label ?? props.placeholder}
        {...props}
        style={[
          t.font.body,
          {
            color: t.colors.text,
            backgroundColor: t.colors.surfaceAlt,
            borderRadius: t.radius.md,
            paddingHorizontal: t.spacing.md,
            paddingVertical: 10,
            borderWidth: StyleSheet.hairlineWidth,
            borderColor: t.colors.border,
          },
          style,
        ]}
      />
      {hint ? <SText variant="caption" color="subtle">{hint}</SText> : null}
    </View>
  );
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: t.spacing.sm }}>
      <SText variant="caption" color="muted" style={{ fontWeight: '700', letterSpacing: 0.6 }}>
        {typeof children === 'string' ? children.toUpperCase() : children}
      </SText>
      {right}
    </View>
  );
}

export function EmptyState({
  icon = 'file-tray-outline',
  title,
  message,
  action,
}: {
  icon?: IconName;
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  const t = useTheme();
  return (
    <View style={{ alignItems: 'center', padding: t.spacing.xxl, gap: t.spacing.sm }}>
      <View
        style={{
          width: 56,
          height: 56,
          borderRadius: 28,
          backgroundColor: t.colors.accentSoft,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Ionicons name={icon} size={26} color={t.colors.accent} />
      </View>
      <SText variant="title">{title}</SText>
      {message ? (
        <SText color="muted" style={{ textAlign: 'center' }}>
          {message}
        </SText>
      ) : null}
      {action}
    </View>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <EmptyState
      icon="cloud-offline-outline"
      title="Couldn't reach Side"
      message={`${message}\nCheck the API base URL in Settings, or turn on mock mode.`}
      action={onRetry ? <Button title="Retry" variant="secondary" onPress={onRetry} icon="refresh" /> : undefined}
    />
  );
}

export function Row({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[{ flexDirection: 'row', alignItems: 'center' }, style]}>{children}</View>;
}
