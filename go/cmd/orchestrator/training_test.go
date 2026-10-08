package main

import (
	"testing"

	pb "github.com/DYNAMOS-UVA/DYNAMOS/pkg/proto"
	"google.golang.org/protobuf/types/known/structpb"
)

func TestTrainingRequiresEveryOrganizationAndLocalArchetype(t *testing.T) {
	metadata, _ := structpb.NewStruct(map[string]interface{}{
		"algorithm": "logistic-regression-v1", "dataset_id": "synthetic-local-v1",
		"organizations": []interface{}{"UVA", "TUDELFT"}, "rounds": 3, "local_epochs": 2,
	})
	response := &pb.ValidationResponse{RequestApproved: true, Training: metadata,
		ValidDataproviders: map[string]*pb.DataProvider{
			"UVA": {Archetypes: []string{"computeToData"}}, "TUDELFT": {Archetypes: []string{"computeToData"}},
		}}
	if err := validateTrainingApproval(response); err != nil {
		t.Fatal(err)
	}
	delete(response.ValidDataproviders, "TUDELFT")
	if validateTrainingApproval(response) == nil {
		t.Fatal("partially authorized training accepted")
	}
	response.ValidDataproviders["TUDELFT"] = &pb.DataProvider{Archetypes: []string{"dataThroughTtp"}}
	if validateTrainingApproval(response) == nil {
		t.Fatal("data transfer archetype accepted for local training")
	}
}
