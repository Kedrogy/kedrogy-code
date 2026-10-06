"""Regression checks for meaningful training and honest validation metrics."""
import unittest
import pandas as pd
from kedrogy_contracts.training import training_options
from mykedro.quality import quality_report
from mykedro.pipelines.train.nodes import split_examples


class TrainingQualityTests(unittest.TestCase):
    def test_default_training_has_multiple_epochs_and_rejects_invalid_options(self):
        options = training_options({})
        self.assertGreater(options['num_train_epochs'], 1)
        self.assertEqual(options['max_steps'], -1)
        for overrides in [{'num_train_epochs':0},{'learning_rate':float('nan')},{'max_steps':0},
                          {'train_batch_size':True},{'typo':8},[],{'max_length':1024}]:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                training_options(overrides)
        self.assertEqual(training_options({'max_steps':1})['max_steps'],1)

    def test_collapsed_predictor_is_reported_even_with_high_accuracy(self):
        report = quality_report([0,1,1,1,1], [1,1,1,1,1], classes=2, training_steps=1, train_samples=15)
        self.assertEqual(report['accuracy'], .8)
        self.assertEqual(report['majority_baseline'], .8)
        self.assertEqual(report['confusion_matrix'], [[0,1],[0,4]])
        self.assertIn('missing_predicted_classes', report['warnings'])
        self.assertIn('not_above_majority_baseline', report['warnings'])
        self.assertIn('few_training_steps', report['warnings'])

    def test_perfect_small_validation_still_requires_review(self):
        report = quality_report([0,1,0,1],[0,1,0,1],classes=2,training_steps=80,train_samples=40)
        self.assertEqual(report['macro_f1'],1)
        self.assertEqual(report['warnings'],['small_validation_sample'])

    def test_split_deduplicates_text_and_keeps_classes_in_both_partitions(self):
        rows = pd.DataFrame([{'text':f'Class {c} example {i}','label':c} for c in range(2) for i in range(8)])
        rows = pd.concat([rows, pd.DataFrame([{'text':' CLASS  0 example 0 ','label':0}])])
        train, validation = split_examples(rows, {'data_seed':123})
        self.assertEqual(len(train)+len(validation),16)
        self.assertFalse(set(train.text) & set(validation.text))
        self.assertEqual(set(train.label), {0,1})
        self.assertEqual(set(validation.label), {0,1})
        duplicate = pd.DataFrame([{'text':'Class 0 example 0','label':1}])
        with self.assertRaises(ValueError):
            split_examples(pd.concat([rows,duplicate]), {'data_seed':123})

if __name__ == '__main__':
    unittest.main()
