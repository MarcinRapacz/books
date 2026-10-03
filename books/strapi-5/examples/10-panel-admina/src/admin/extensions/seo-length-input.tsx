import * as React from 'react';
import { Field, Flex, TextInput, Textarea, Typography } from '@strapi/design-system';
import { useField, useFocusInputField } from '@strapi/strapi/admin';

interface SeoLengthInputProps {
  name: string;
  label: string;
  hint?: React.ReactNode;
  required?: boolean;
  disabled?: boolean;
  attribute: {
    type: string;
    maxLength?: number;
    options?: { recommendedLength?: number };
  };
}

const DEFAULT_RECOMMENDED_LENGTH = 60;

const SeoLengthInput = ({ name, label, hint, required, disabled, attribute }: SeoLengthInputProps) => {
  // The Content Manager form owns the value; a custom field only reads and updates it.
  const { value, error, onChange } = useField<string>(name);
  const fieldRef = useFocusInputField<HTMLInputElement & HTMLTextAreaElement>(name);
  const text = value ?? '';
  const recommended = attribute.options?.recommendedLength ?? DEFAULT_RECOMMENDED_LENGTH;
  const isTooLong = text.length > recommended;

  const handleChange = (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    onChange(name, event.target.value);
  };
  const inputProps = { ref: fieldRef, name, value: text, disabled, onChange: handleChange };

  return (
    <Field.Root name={name} hint={hint} error={error} required={required}>
      <Flex justifyContent="space-between">
        <Field.Label>{label}</Field.Label>
        <Typography variant="pi" textColor={isTooLong ? 'danger600' : 'neutral600'}>
          {text.length} / {recommended}
        </Typography>
      </Flex>
      {attribute.type === 'text' ? <Textarea {...inputProps} /> : <TextInput {...inputProps} />}
      <Field.Hint />
      <Field.Error />
    </Field.Root>
  );
};

export default SeoLengthInput;
